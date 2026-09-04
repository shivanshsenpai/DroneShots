"""
FastAPI Server and WebSocket Broadcaster for DJI Tello 3D Autonomous Follow System.
"""
import os
import time
import asyncio
import json
import cv2
import numpy as np
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import ServerConfig, FollowConfig, PIDConfig
from backend.tello_controller import TelloDroneManager
from backend.vision.tracker_3d import UnifiedTracker3D
from backend.navigation.pid_follower import PIDController4Axis
from backend.navigation.kalman_tracker import KalmanTargetFilter
from backend.profiles.profile_store import ProfileStore

# Initialize Core Services
drone_manager = TelloDroneManager()
tracker_3d = UnifiedTracker3D()
pid_controller = PIDController4Axis()
kalman_filter = KalmanTargetFilter()
profile_store = ProfileStore()

# Global State
autonomous_tracking_active = False
active_connections: List[WebSocket] = []
current_tracking_data: Dict[str, Any] = {}
last_rc_output: Dict[str, int] = {"roll": 0, "pitch": 0, "throttle": 0, "yaw": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to simulator or drone
    print("[APP] Starting Drone Follow Server...")
    drone_manager.connect(prefer_physical=False)
    # Start background loop for follow control
    asyncio.create_task(autonomous_control_loop())
    yield
    # Shutdown
    print("[APP] Shutting down...")
    drone_manager.stop()


app = FastAPI(title="DJI Tello 3D Follow Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def autonomous_control_loop():
    """Background loop that updates tracking and sends PID commands to the drone."""
    global current_tracking_data, last_rc_output, autonomous_tracking_active
    while True:
        try:
            frame = drone_manager.get_frame()
            if frame is not None:
                # 1. Process 3D tracking & orientation
                track_result = tracker_3d.process_and_track(frame)
                current_tracking_data = track_result

                # 2. If Autonomous Tracking is ON and drone is flying
                if autonomous_tracking_active:
                    rc_cmds = pid_controller.compute_rc_velocities(track_result)
                    last_rc_output = rc_cmds
                    drone_manager.send_rc_control(
                        roll=rc_cmds["roll"],
                        pitch=rc_cmds["pitch"],
                        throttle=rc_cmds["throttle"],
                        yaw=rc_cmds["yaw"]
                    )
                else:
                    last_rc_output = {"roll": 0, "pitch": 0, "throttle": 0, "yaw": 0}

            await asyncio.sleep(0.033)  # ~30 Hz
        except Exception as e:
            await asyncio.sleep(0.05)


def generate_mjpeg_stream():
    """Streams MJPEG frames with dynamic visual bounding overlays."""
    while True:
        frame = drone_manager.get_frame()
        if frame is None:
            time.sleep(0.03)
            continue

        # Draw light HUD tracking indicator on the stream frame
        if current_tracking_data and current_tracking_data.get("target_detected"):
            bbox = current_tracking_data.get("bbox")
            if bbox:
                x, y, w, h = bbox
                is_matched = current_tracking_data.get("target_matched", False)
                color = (0, 255, 163) if is_matched else (0, 240, 255) # Emerald vs Cyan
                
                # Corner bracket reticles
                length = min(20, w // 4, h // 4)
                # Top-Left
                cv2.line(frame, (x, y), (x + length, y), color, 2)
                cv2.line(frame, (x, y), (x, y + length), color, 2)
                # Top-Right
                cv2.line(frame, (x + w, y), (x + w - length, y), color, 2)
                cv2.line(frame, (x + w, y), (x + w, y + length), color, 2)
                # Bottom-Left
                cv2.line(frame, (x, y + h), (x + length, y + h), color, 2)
                cv2.line(frame, (x, y + h), (x, y + h - length), color, 2)
                # Bottom-Right
                cv2.line(frame, (x + w, y + h), (x + w - length, y + h), color, 2)
                cv2.line(frame, (x + w, y + h), (x + w, y + h - length), color, 2)

                # Info Label
                conf = int(current_tracking_data.get("confidence", 0) * 100)
                orient = current_tracking_data.get("orientation", "")
                dist = current_tracking_data.get("estimated_distance_m", 0.0)
                label = f"TARGET LOCKED [{orient}] {dist:.1f}m ({conf}%)" if is_matched else f"DETECTED [{orient}]"
                cv2.putText(frame, label, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ret:
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.033)


@app.get("/api/video_feed")
def video_feed():
    """Endpoint for low-latency live video stream."""
    return StreamingResponse(
        generate_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# -------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------

class ConnectRequest(BaseModel):
    prefer_physical: bool = False

@app.post("/api/connect")
def connect_drone(req: ConnectRequest):
    """Connects to Physical DJI Tello or Simulator."""
    res = drone_manager.connect(prefer_physical=req.prefer_physical)
    return res


@app.post("/api/scan")
def scan_target(name: str = Body(default="Subject Alpha", embed=True)):
    """
    Scans the current person in frame and extracts 360° 3D biometrics,
    skeletal landmarks, color palette, and proportions for confirmation.
    """
    frame = drone_manager.get_frame()
    if frame is None:
        raise HTTPException(status_code=400, detail="No video frame available from drone")

    profile = tracker_3d.generate_scan_profile(frame, name=name)
    if not profile:
        raise HTTPException(status_code=422, detail="No subject detected in frame. Please stand in view of the camera.")

    return {
        "status": "success",
        "profile": profile
    }


class RegisterTargetRequest(BaseModel):
    profile: Dict[str, Any]
    lock_immediately: bool = True

@app.post("/api/register_target")
def register_target(req: RegisterTargetRequest):
    """Saves a confirmed 3D profile to database and optionally locks onto it."""
    pid = profile_store.save_profile(req.profile)
    if req.lock_immediately:
        tracker_3d.set_locked_target(req.profile)
    return {"status": "registered", "profile_id": pid, "is_locked": req.lock_immediately}


@app.post("/api/lock_target/{profile_id}")
def lock_target_by_id(profile_id: str):
    """Locks onto an existing stored profile by ID."""
    prof = profile_store.get_profile(profile_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")
    tracker_3d.set_locked_target(prof)
    return {"status": "locked", "profile": prof}


@app.post("/api/unlock_target")
def unlock_target():
    """Unlocks current target."""
    tracker_3d.set_locked_target(None)
    return {"status": "unlocked"}


@app.get("/api/profiles")
def get_profiles():
    """Lists all stored target profiles."""
    return profile_store.list_profiles()


@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: str):
    """Deletes a profile."""
    success = profile_store.delete_profile(profile_id)
    return {"status": "deleted" if success else "failed"}


class FollowSettingsRequest(BaseModel):
    mode: Optional[str] = None
    target_distance_m: Optional[float] = None
    target_altitude_m: Optional[float] = None
    kp_yaw: Optional[float] = None
    kd_yaw: Optional[float] = None
    kp_pitch: Optional[float] = None
    kd_pitch: Optional[float] = None
    kp_throttle: Optional[float] = None
    kd_throttle: Optional[float] = None

@app.post("/api/settings/follow")
def update_follow_settings(req: FollowSettingsRequest):
    """Updates follow mode, setpoint distance/altitude, and PID gains."""
    if req.mode:
        pid_controller.set_mode(req.mode)
    pid_controller.set_parameters(req.target_distance_m, req.target_altitude_m)
    gains = {}
    if req.kp_yaw is not None: gains["kp_yaw"] = req.kp_yaw
    if req.kd_yaw is not None: gains["kd_yaw"] = req.kd_yaw
    if req.kp_pitch is not None: gains["kp_pitch"] = req.kp_pitch
    if req.kd_pitch is not None: gains["kd_pitch"] = req.kd_pitch
    if req.kp_throttle is not None: gains["kp_throttle"] = req.kp_throttle
    if req.kd_throttle is not None: gains["kd_throttle"] = req.kd_throttle
    if gains:
        pid_controller.update_gains(gains)
    return {
        "status": "updated",
        "mode": pid_controller.mode,
        "target_distance_m": pid_controller.target_distance_m,
        "target_altitude_m": pid_controller.target_altitude_m
    }


class FollowModeRequest(BaseModel):
    mode: str  # "LEAD", "CHASE", "FLANK_LEFT", "FLANK_RIGHT", "ORBIT"
    target_distance_m: Optional[float] = 2.0

@app.post("/api/follow_mode")
def set_follow_mode(req: FollowModeRequest):
    """Sets follow perspective."""
    pid_controller.set_mode(req.mode)
    if req.target_distance_m:
        pid_controller.set_parameters(distance_m=req.target_distance_m)
    return {"status": "updated", "mode": pid_controller.mode, "distance_m": pid_controller.target_distance_m}


class TrackingToggleRequest(BaseModel):
    active: bool

@app.post("/api/tracking_toggle")
def toggle_autonomous_tracking(req: TrackingToggleRequest):
    """Toggles Autonomous Follow on or off."""
    global autonomous_tracking_active
    autonomous_tracking_active = req.active
    if not req.active:
        drone_manager.send_rc_control(0, 0, 0, 0)
    return {"status": "updated", "autonomous_tracking_active": autonomous_tracking_active}


# Flight Commands
@app.post("/api/flight/takeoff")
def flight_takeoff():
    res = drone_manager.takeoff()
    return {"status": "success" if res else "failed"}


@app.post("/api/flight/land")
def flight_land():
    global autonomous_tracking_active
    autonomous_tracking_active = False
    res = drone_manager.land()
    return {"status": "success" if res else "failed"}


@app.post("/api/flight/emergency")
def flight_emergency():
    global autonomous_tracking_active
    autonomous_tracking_active = False
    drone_manager.emergency()
    return {"status": "emergency_stop_triggered"}


@app.post("/api/flight/flip/{direction}")
def flight_flip(direction: str):
    """Performs an acrobatic flip (f, b, l, r)."""
    if direction.lower() not in ["f", "b", "l", "r"]:
        raise HTTPException(status_code=400, detail="Direction must be 'f', 'b', 'l', or 'r'")
    res = drone_manager.flip(direction.lower())
    return {"status": "success" if res else "failed", "flip": direction.lower()}


@app.post("/api/flight/snapshot")
def capture_snapshot():
    """Captures and saves a high-res snapshot of current drone camera feed."""
    frame = drone_manager.get_frame()
    if frame is None:
        raise HTTPException(status_code=400, detail="No video frame available")

    snapshots_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)
    filename = f"snap_{int(time.time() * 1000)}.jpg"
    filepath = os.path.join(snapshots_dir, filename)

    # Annotate frame with high-tech timestamp & telemetry watermark
    annotated = frame.copy()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(annotated, f"AERO-FOLLOW 3D // {ts}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    if current_tracking_data.get("target_detected"):
        orient = current_tracking_data.get("orientation", "")
        dist = current_tracking_data.get("estimated_distance_m", 0.0)
        cv2.putText(annotated, f"TARGET: {orient} | DIST: {dist:.1f}m", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    cv2.imwrite(filepath, annotated, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return {"status": "captured", "filename": filename, "url": f"/snapshots/{filename}"}


class ManualRCRequest(BaseModel):
    roll: int = 0
    pitch: int = 0
    throttle: int = 0
    yaw: int = 0

@app.post("/api/flight/manual_rc")
def manual_rc(req: ManualRCRequest):
    """Sends direct manual joystick commands."""
    global autonomous_tracking_active
    if not autonomous_tracking_active:
        drone_manager.send_rc_control(req.roll, req.pitch, req.throttle, req.yaw)
    return {"status": "ok", "rc": req.model_dump()}


# -------------------------------------------------------------
# WebSocket Telemetry & 3D Tracking Stream (20 Hz)
# -------------------------------------------------------------

@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            telem = drone_manager.get_telemetry()
            payload = {
                "telemetry": telem,
                "tracking": current_tracking_data,
                "rc_commands": last_rc_output,
                "autonomous_active": autonomous_tracking_active,
                "follow_mode": pid_controller.mode,
                "timestamp": time.time()
            }
            await websocket.send_json(payload)
            await asyncio.sleep(0.05) # 20Hz update rate
    except (WebSocketDisconnect, Exception):
        if websocket in active_connections:
            active_connections.remove(websocket)


# Serve captured snapshots
snapshots_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "snapshots")
os.makedirs(snapshots_dist, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=snapshots_dist), name="snapshots")

# Serve built frontend if exists
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
