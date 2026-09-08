"""
DJI Ryze Tello Controller with Dual-Source Support:
1. System Webcam (Integrated / USB Cameras with DirectShow low-latency capture & Virtual Drone simulation)
2. Physical DJI Ryze Tello Drone (Wi-Fi UDP connection with djitellopy)
"""
import time
import math
import threading
import socket
import cv2
import numpy as np
from typing import Optional, Dict, Any, List

try:
    from djitellopy import Tello
    TELLO_AVAILABLE = True
except ImportError:
    TELLO_AVAILABLE = False


class TelloDroneManager:
    def __init__(self):
        self.drone: Optional[Any] = None
        self.current_source: str = "WEBCAM"  # "WEBCAM" or "DRONE_WIFI"
        self.camera_index: int = 0
        self.is_connected: bool = False
        self.is_simulator: bool = True
        self.is_flying: bool = False
        self.camera_cap: Optional[cv2.VideoCapture] = None

        # Frame buffering
        self.current_frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()
        self.running: bool = False
        self.stream_thread: Optional[threading.Thread] = None

        # Simulated Telemetry State (For Webcam / Virtual Flight Mode)
        self.sim_state = {
            "battery": 95,
            "altitude_cm": 0,
            "flight_time_sec": 0,
            "temp_c": 36,
            "wifi_signal": 95,
            "pitch_deg": 0.0,
            "roll_deg": 0.0,
            "yaw_deg": 0.0,
            "speed_x": 0,
            "speed_y": 0,
            "speed_z": 0,
            "barometer_m": 0.0,
            "tof_cm": 0
        }
        self.sim_start_time = 0.0
        self.last_rc = {"roll": 0, "pitch": 0, "throttle": 0, "yaw": 0}

    @staticmethod
    def get_available_cameras() -> List[Dict[str, Any]]:
        """Quickly probes system camera devices (indices 0 to 2) using DirectShow."""
        found = []
        for idx in range(3):
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap.isOpened():
                    found.append({
                        "index": idx,
                        "name": f"System Camera {idx}" if idx > 0 else "Integrated / Primary Webcam"
                    })
                    cap.release()
            except Exception:
                pass
        return found if found else [{"index": 0, "name": "Primary Webcam"}]

    def set_source(self, source: str, camera_index: int = 0) -> Dict[str, Any]:
        """
        Switches between System Webcam and Physical DJI Tello Drone over Wi-Fi.
        """
        source_upper = source.upper()

        if source_upper == "DRONE_WIFI":
            return self._connect_physical_tello()
        else:
            return self._connect_webcam(camera_index=camera_index)

    def connect(self, prefer_physical: bool = False, camera_index: int = 0) -> Dict[str, Any]:
        """Backward-compatible connection trigger."""
        if prefer_physical:
            return self.set_source("DRONE_WIFI")
        return self.set_source("WEBCAM", camera_index=camera_index)

    def _connect_webcam(self, camera_index: int = 0) -> Dict[str, Any]:
        """Initializes system webcam stream with zero-latency buffer."""
        print(f"[TELLO_MGR] Initializing System Webcam (Cam {camera_index})...")
        self.stop()

        self.current_source = "WEBCAM"
        self.camera_index = camera_index
        self.is_simulator = True
        self.is_connected = True
        self.running = True
        self.sim_start_time = time.time()

        # Try DirectShow first on Windows for instant initialization without MSMF hang
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(camera_index)

        if cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)
            self.camera_cap = cap
            print(f"[TELLO_MGR] Webcam {camera_index} opened successfully.")
        else:
            print(f"[TELLO_MGR] Webcam {camera_index} could not be opened. Using synthetic stream.")
            self.camera_cap = None

        self.stream_thread = threading.Thread(target=self._webcam_stream_worker, daemon=True)
        self.stream_thread.start()

        return {
            "status": "connected",
            "source": "WEBCAM",
            "camera_index": camera_index,
            "is_flying": self.is_flying,
            "battery": int(self.sim_state["battery"]),
            "message": f"Active: System Webcam {camera_index} (Virtual Flight Simulation Enabled)"
        }

    def _connect_physical_tello(self) -> Dict[str, Any]:
        """Attempts to connect to a physical DJI Tello drone over Wi-Fi."""
        if not TELLO_AVAILABLE:
            return {
                "status": "error",
                "source": self.current_source,
                "message": "djitellopy library is not available in Python environment."
            }

        print("[TELLO_MGR] Attempting connection to DJI Ryze Tello via Wi-Fi...")
        
        drone = None
        try:
            Tello.RESPONSE_TIMEOUT = 2
            Tello.RETRY_COUNT = 1
            drone = Tello(retry_count=1)
            drone.RESPONSE_TIMEOUT = 2
            drone.connect()
            drone.streamon()
        except Exception as e:
            err_msg = str(e)
            print(f"[TELLO_MGR] Physical Tello connection failed: {err_msg}")
            if drone:
                try:
                    drone.end()
                except Exception:
                    pass
            
            # If we were already running webcam, keep webcam alive
            if not self.running:
                self._connect_webcam(self.camera_index)

            return {
                "status": "error",
                "source": self.current_source,
                "message": f"Could not reach DJI Tello. Ensure drone is ON and PC Wi-Fi is connected to TELLO-XXXXXX. ({err_msg})",
                "suggested_action": "Switch to System Webcam or connect Wi-Fi"
            }

        # Successfully connected to physical drone
        self.stop()
        self.drone = drone
        self.current_source = "DRONE_WIFI"
        self.is_connected = True
        self.is_simulator = False
        self.running = True

        self.stream_thread = threading.Thread(target=self._physical_stream_worker, daemon=True)
        self.stream_thread.start()

        try:
            battery = drone.get_battery()
        except Exception:
            battery = 100

        return {
            "status": "connected",
            "source": "DRONE_WIFI",
            "battery": battery,
            "message": "Connected to physical DJI Tello over Wi-Fi!"
        }

    def _webcam_stream_worker(self):
        """Worker thread for webcam video feed and simulated drone flight physics."""
        sim_step = 0
        while self.running:
            sim_step += 1
            frame = None
            if self.camera_cap and self.camera_cap.isOpened():
                ret, cam_frame = self.camera_cap.read()
                if ret and cam_frame is not None:
                    # Mirror horizontally for natural webcam interaction
                    frame = cv2.flip(cam_frame, 1)

            if frame is None:
                # High-tech synthetic fallback frame if webcam is blocked
                frame = self._generate_synthetic_frame(sim_step)

            with self.frame_lock:
                self.current_frame = frame.copy()

            self._update_sim_physics()
            time.sleep(0.033)  # ~30 FPS

    def _physical_stream_worker(self):
        """Worker thread that continuously polls frames from the physical DJI Tello."""
        try:
            frame_reader = self.drone.get_frame_read()
        except Exception as e:
            print(f"[TELLO_MGR] Frame reader error: {e}")
            return

        while self.running:
            try:
                frame = frame_reader.frame
                if frame is not None:
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR) if len(frame.shape) == 3 else frame
                    with self.frame_lock:
                        self.current_frame = frame_bgr.copy()
                time.sleep(0.02)
            except Exception:
                time.sleep(0.05)

    def _generate_synthetic_frame(self, step: int) -> np.ndarray:
        """Draws high-tech cyber calibration grid when no video sensor is available."""
        h, w = 720, 960
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:] = (10, 12, 16)

        grid_size = 40
        offset = (step * 2) % grid_size
        for x in range(0, w, grid_size):
            cv2.line(img, (x, 0), (x, h), (24, 28, 36), 1)
        for y in range(0, h, grid_size):
            cv2.line(img, (0, (y + offset) % h), (w, (y + offset) % h), (24, 28, 36), 1)

        cx = int(w * 0.5 + 70 * math.sin(step * 0.03))
        cy = int(h * 0.45 + 25 * math.cos(step * 0.02))

        # Head
        cv2.circle(img, (cx, cy - 80), 30, (230, 230, 230), -1)
        cv2.circle(img, (cx, cy - 80), 32, (255, 255, 255), 1)
        # Hair
        cv2.ellipse(img, (cx, cy - 95), (26, 16), 0, 180, 360, (35, 30, 30), -1)
        # Torso
        cv2.rectangle(img, (cx - 40, cy - 40), (cx + 40, cy + 55), (180, 180, 180), -1)
        # Legs
        cv2.rectangle(img, (cx - 35, cy + 55), (cx - 10, cy + 170), (45, 45, 55), -1)
        cv2.rectangle(img, (cx + 10, cy + 55), (cx + 35, cy + 170), (45, 45, 55), -1)

        cv2.putText(img, "SYNTHETIC TARGET SIMULATION", (w // 2 - 130, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1, cv2.LINE_AA)
        return img

    def _update_sim_physics(self):
        """Simulates realistic telemetry adjustments based on RC controls and flight state."""
        if not self.is_flying:
            self.sim_state["altitude_cm"] = 0
            self.sim_state["tof_cm"] = 0
            self.sim_state["barometer_m"] = 0.0
            self.sim_state["pitch_deg"] = 0.0
            self.sim_state["roll_deg"] = 0.0
            return

        self.sim_state["flight_time_sec"] = int(time.time() - self.sim_start_time)

        # Battery slow consumption
        if self.sim_state["battery"] > 10:
            self.sim_state["battery"] -= 0.002

        # Altitude reaction to throttle command
        throttle = self.last_rc["throttle"]
        self.sim_state["altitude_cm"] = max(20, min(300, int(self.sim_state["altitude_cm"] + throttle * 0.15)))
        self.sim_state["tof_cm"] = self.sim_state["altitude_cm"]
        self.sim_state["barometer_m"] = round(self.sim_state["altitude_cm"] / 100.0, 2)

        # Attitude tilt reaction to pitch and roll commands
        self.sim_state["pitch_deg"] = round(self.last_rc["pitch"] * 0.35, 1)
        self.sim_state["roll_deg"] = round(self.last_rc["roll"] * 0.35, 1)
        self.sim_state["yaw_deg"] = round((self.sim_state["yaw_deg"] + self.last_rc["yaw"] * 0.2) % 360, 1)

    def get_frame(self) -> Optional[np.ndarray]:
        """Returns the latest captured frame."""
        with self.frame_lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
        return None

    def send_rc_control(self, roll: int, pitch: int, throttle: int, yaw: int):
        """Sends velocity commands (-100 to 100) to the drone or virtual simulation."""
        self.last_rc = {"roll": roll, "pitch": pitch, "throttle": throttle, "yaw": yaw}

        if not self.is_simulator and self.drone and self.is_connected:
            try:
                self.drone.send_rc_control(roll, pitch, throttle, yaw)
            except Exception as e:
                print(f"[TELLO_MGR] Error sending RC command: {e}")

    def takeoff(self) -> bool:
        """Commands drone to takeoff."""
        self.is_flying = True
        if not self.is_simulator and self.drone and self.is_connected:
            try:
                self.drone.takeoff()
                return True
            except Exception as e:
                print(f"[TELLO_MGR] Takeoff error: {e}")
                return False
        else:
            self.sim_state["altitude_cm"] = 120
            self.sim_start_time = time.time()
            return True

    def land(self) -> bool:
        """Commands drone to land."""
        self.is_flying = False
        self.send_rc_control(0, 0, 0, 0)
        if not self.is_simulator and self.drone and self.is_connected:
            try:
                self.drone.land()
                return True
            except Exception as e:
                print(f"[TELLO_MGR] Land error: {e}")
                return False
        else:
            self.sim_state["altitude_cm"] = 0
            return True

    def flip(self, direction: str = "f") -> bool:
        """Flips drone in direction ('f', 'b', 'l', 'r')."""
        if not self.is_flying:
            return False
        if not self.is_simulator and self.drone and self.is_connected:
            try:
                self.drone.flip(direction)
                return True
            except Exception as e:
                print(f"[TELLO_MGR] Flip error: {e}")
                return False
        else:
            print(f"[TELLO_MGR SIM] Simulated flip: {direction}")
            return True

    def emergency(self):
        """Emergency cutoff motors."""
        self.is_flying = False
        self.send_rc_control(0, 0, 0, 0)
        if not self.is_simulator and self.drone and self.is_connected:
            try:
                self.drone.emergency()
            except Exception:
                pass

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns current flight telemetry state."""
        if not self.is_simulator and self.drone and self.is_connected:
            try:
                return {
                    "connected": True,
                    "source": "DRONE_WIFI",
                    "mode": "PHYSICAL_TELLO",
                    "is_flying": self.is_flying,
                    "battery": self.drone.get_battery(),
                    "altitude_cm": self.drone.get_height(),
                    "flight_time_sec": self.drone.get_flight_time(),
                    "temp_c": self.drone.get_temperature(),
                    "wifi_signal": 95,
                    "pitch_deg": self.drone.get_pitch(),
                    "roll_deg": self.drone.get_roll(),
                    "yaw_deg": self.drone.get_yaw(),
                    "speed_x": self.drone.get_speed_x(),
                    "speed_y": self.drone.get_speed_y(),
                    "speed_z": self.drone.get_speed_z(),
                    "barometer_m": round(self.drone.get_barometer() / 100.0, 2),
                    "tof_cm": self.drone.get_distance_tof(),
                    "rc_commands": self.last_rc
                }
            except Exception:
                pass

        # Return simulated telemetry for webcam mode
        return {
            "connected": self.is_connected,
            "source": self.current_source,
            "mode": "WEBCAM" if self.current_source == "WEBCAM" else "SIMULATOR",
            "camera_index": self.camera_index,
            "is_flying": self.is_flying,
            "battery": int(self.sim_state["battery"]),
            "altitude_cm": self.sim_state["altitude_cm"],
            "flight_time_sec": self.sim_state["flight_time_sec"],
            "temp_c": self.sim_state["temp_c"],
            "wifi_signal": self.sim_state["wifi_signal"],
            "pitch_deg": self.sim_state["pitch_deg"],
            "roll_deg": self.sim_state["roll_deg"],
            "yaw_deg": self.sim_state["yaw_deg"],
            "speed_x": self.sim_state["speed_x"],
            "speed_y": self.sim_state["speed_y"],
            "speed_z": self.sim_state["speed_z"],
            "barometer_m": self.sim_state["barometer_m"],
            "tof_cm": self.sim_state["tof_cm"],
            "rc_commands": self.last_rc
        }

    def stop(self):
        """Stops stream threads and releases cameras or drone connections."""
        self.running = False
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=1.0)

        if self.camera_cap:
            try:
                self.camera_cap.release()
            except Exception:
                pass
            self.camera_cap = None

        if self.drone:
            try:
                self.drone.end()
            except Exception:
                pass
            self.drone = None

        self.is_connected = False
