"""
DJI Ryze Tello Controller with Virtual Drone / Webcam Simulator Failover.
Provides high-performance frame streaming, smooth RC command transmission,
and 20Hz telemetry aggregation.
"""
import time
import math
import threading
import cv2
import numpy as np
from typing import Optional, Dict, Any

try:
    from djitellopy import Tello
    TELLO_AVAILABLE = True
except ImportError:
    TELLO_AVAILABLE = False


class TelloDroneManager:
    def __init__(self):
        self.drone: Optional[Any] = None
        self.is_connected: bool = False
        self.is_simulator: bool = True
        self.is_flying: bool = False
        self.camera_cap: Optional[cv2.VideoCapture] = None
        
        # Frame buffering
        self.current_frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.stream_thread: Optional[threading.Thread] = None

        # Simulated Telemetry State
        self.sim_state = {
            "battery": 94,
            "altitude_cm": 0,
            "flight_time_sec": 0,
            "temp_c": 36,
            "wifi_signal": 92,
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

    def connect(self, prefer_physical: bool = False) -> Dict[str, Any]:
        """
        Attempts to connect to a physical DJI Tello drone over Wi-Fi.
        If unavailable or if simulator is requested, starts Virtual Drone / Webcam mode.
        """
        self.stop()

        if prefer_physical and TELLO_AVAILABLE:
            try:
                print("[TELLO] Attempting connection to physical DJI Tello...")
                drone = Tello()
                drone.connect()
                drone.streamon()
                self.drone = drone
                self.is_connected = True
                self.is_simulator = False
                self.running = True
                self.stream_thread = threading.Thread(target=self._physical_stream_worker, daemon=True)
                self.stream_thread.start()
                return {"status": "connected", "mode": "PHYSICAL_TELLO", "battery": drone.get_battery()}
            except Exception as e:
                print(f"[TELLO] Physical connection failed ({e}). Falling back to Virtual Simulator...")

        # Fallback to Webcam / Simulator Mode
        print("[TELLO] Initializing Virtual Drone Simulator & Camera...")
        self.is_simulator = True
        self.is_connected = True
        self.running = True
        self.sim_start_time = time.time()

        # Try to open webcam (0 or 1)
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            cap = cv2.VideoCapture(1)

        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)
            self.camera_cap = cap
        else:
            self.camera_cap = None

        self.stream_thread = threading.Thread(target=self._simulator_stream_worker, daemon=True)
        self.stream_thread.start()

        return {"status": "connected", "mode": "SIMULATOR", "battery": self.sim_state["battery"]}

    def _physical_stream_worker(self):
        """Worker thread that continuously polls frames from the physical DJI Tello."""
        frame_reader = self.drone.get_frame_read()
        while self.running:
            try:
                frame = frame_reader.frame
                if frame is not None:
                    # Tello frames are usually RGB, convert to BGR for OpenCV processing
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR) if len(frame.shape) == 3 else frame
                    with self.frame_lock:
                        self.current_frame = frame_bgr.copy()
                time.sleep(0.02)
            except Exception as e:
                time.sleep(0.05)

    def _simulator_stream_worker(self):
        """Worker thread for webcam or synthetic HUD generator."""
        sim_step = 0
        while self.running:
            sim_step += 1
            frame = None
            if self.camera_cap and self.camera_cap.isOpened():
                ret, cam_frame = self.camera_cap.read()
                if ret and cam_frame is not None:
                    frame = cv2.flip(cam_frame, 1)  # Mirror webcam for natural interaction

            if frame is None:
                # Generate high-tech synthetic drone video feed if no webcam
                frame = self._generate_synthetic_drone_frame(sim_step)

            with self.frame_lock:
                self.current_frame = frame.copy()

            # Update simulated physics
            self._update_sim_physics()
            time.sleep(0.033)

    def _generate_synthetic_drone_frame(self, step: int) -> np.ndarray:
        """Generates synthetic high-tech grid frame if no camera is available."""
        h, w = 720, 960
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:] = (12, 16, 24)

        # Draw tech grid
        grid_size = 40
        offset = (step * 2) % grid_size
        for x in range(0, w, grid_size):
            cv2.line(img, (x, 0), (x, h), (25, 35, 50), 1)
        for y in range(0, h, grid_size):
            cv2.line(img, (0, (y + offset) % h), (w, (y + offset) % h), (25, 35, 50), 1)

        # Draw a simulated subject moving gently in 3D
        cx = int(w * 0.5 + 80 * math.sin(step * 0.03))
        cy = int(h * 0.45 + 30 * math.cos(step * 0.02))
        
        # Head
        cv2.circle(img, (cx, cy - 80), 32, (200, 200, 200), -1)
        cv2.circle(img, (cx, cy - 80), 32, (0, 240, 255), 2)
        # Hair
        cv2.ellipse(img, (cx, cy - 100), (28, 18), 0, 180, 360, (30, 20, 20), -1)
        # Torso
        cv2.rectangle(img, (cx - 45, cy - 40), (cx + 45, cy + 60), (255, 140, 0), -1)
        # Legs
        cv2.rectangle(img, (cx - 40, cy + 60), (cx - 10, cy + 180), (80, 40, 20), -1)
        cv2.rectangle(img, (cx + 10, cy + 60), (cx + 40, cy + 180), (80, 40, 20), -1)

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

        # Flight time
        self.sim_state["flight_time_sec"] = int(time.time() - self.sim_start_time)
        
        # Slow battery decay
        if self.sim_state["battery"] > 10:
            self.sim_state["battery"] -= 0.003

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
        """Sends velocity commands (-100 to 100) to the drone."""
        self.last_rc = {"roll": roll, "pitch": pitch, "throttle": throttle, "yaw": yaw}

        if not self.is_simulator and self.drone and self.is_connected:
            try:
                self.drone.send_rc_control(roll, pitch, throttle, yaw)
            except Exception as e:
                print(f"[TELLO] Error sending RC command: {e}")

    def takeoff(self) -> bool:
        """Commands drone to takeoff."""
        self.is_flying = True
        if not self.is_simulator and self.drone and self.is_connected:
            try:
                self.drone.takeoff()
                return True
            except Exception as e:
                print(f"[TELLO] Takeoff error: {e}")
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
                print(f"[TELLO] Land error: {e}")
                return False
        else:
            self.sim_state["altitude_cm"] = 0
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

        # Return simulated telemetry
        return {
            "connected": self.is_connected,
            "mode": "SIMULATOR" if self.is_simulator else "PHYSICAL_TELLO",
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
        """Stops threads and closes camera/drone connections."""
        self.running = False
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=1.0)

        if self.camera_cap:
            self.camera_cap.release()
            self.camera_cap = None

        if self.drone:
            try:
                self.drone.end()
            except Exception:
                pass
            self.drone = None

        self.is_connected = False
