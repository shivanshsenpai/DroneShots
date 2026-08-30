"""
Configuration settings for the DJI Ryze Tello 3D Autonomous Follow System.
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass
class VisionConfig:
    # Frame processing dimensions
    FRAME_WIDTH: int = 960
    FRAME_HEIGHT: int = 720
    PROCESS_WIDTH: int = 640
    PROCESS_HEIGHT: int = 480
    FPS: int = 30
    
    # Pose estimation confidence thresholds
    MIN_DETECTION_CONFIDENCE: float = 0.55
    MIN_TRACKING_CONFIDENCE: float = 0.55
    
    # ReID and Face Recognition
    FACE_MATCH_THRESHOLD: float = 0.58  # Euclidean distance (lower is stricter)
    COLOR_HIST_WEIGHT: float = 0.45     # Weight for appearance ReID
    POSE_GEOM_WEIGHT: float = 0.25      # Weight for 3D body proportions
    FACE_WEIGHT: float = 0.30           # Weight for facial biometrics
    COMBINED_LOCK_THRESHOLD: float = 0.62  # Score above which target is locked
    
    # Multi-Angle Detection
    HEAD_PITCH_THRESHOLD: float = 25.0  # Degrees
    SHOULDER_YAW_THRESHOLD: float = 30.0 # Degrees


@dataclass
class PIDConfig:
    # Yaw PID (Horizontal alignment - left/right turning)
    KP_YAW: float = 0.42
    KI_YAW: float = 0.00
    KD_YAW: float = 0.18
    
    # Pitch PID (Forward / Backward distance tracking)
    KP_PITCH: float = 0.38
    KI_PITCH: float = 0.00
    KD_PITCH: float = 0.15
    
    # Throttle PID (Vertical alignment - up / down altitude)
    KP_THROTTLE: float = 0.45
    KI_THROTTLE: float = 0.00
    KD_THROTTLE: float = 0.16
    
    # Roll PID (Lateral strafe / orbit)
    KP_ROLL: float = 0.30
    KI_ROLL: float = 0.00
    KD_ROLL: float = 0.12
    
    # Maximum allowable RC command velocities (-100 to 100)
    MAX_SPEED_YAW: int = 50
    MAX_SPEED_PITCH: int = 40
    MAX_SPEED_THROTTLE: int = 45
    MAX_SPEED_ROLL: int = 35
    
    # Deadband margins (pixels / ratios where no command is issued)
    DEADBAND_X: float = 0.06  # ±6% of screen width
    DEADBAND_Y: float = 0.06  # ±6% of screen height
    DEADBAND_AREA: float = 0.04 # ±4% of target bounding box area


@dataclass
class FollowConfig:
    # Target bounding box area as a fraction of screen (0.05 to 0.40)
    # Default ~15% represents approx 1.8 to 2.2 meters distance
    DESIRED_TARGET_AREA: float = 0.15
    TARGET_HEIGHT_RATIO: float = 0.55  # Target should occupy ~55% of vertical height
    
    # Target height vertical center (0.45 = slightly above center for natural perspective)
    DESIRED_CENTER_Y: float = 0.45
    DESIRED_CENTER_X: float = 0.50
    
    # Follow Modes: "LEAD" (front), "CHASE" (back), "FLANK_LEFT", "FLANK_RIGHT", "ORBIT"
    DEFAULT_MODE: str = "LEAD"
    
    # Safety Limits
    MIN_DISTANCE_AREA_LIMIT: float = 0.45  # Too close! Auto-backoff
    MAX_DISTANCE_AREA_LIMIT: float = 0.03  # Too far!
    TARGET_LOST_TIMEOUT_SEC: float = 2.5   # Time before entering search/hover mode
    EMERGENCY_BATTERY_THRESHOLD: int = 15  # Auto-land trigger


@dataclass
class ServerConfig:
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    TELEMETRY_RATE_HZ: int = 20
    PROFILE_DIR: str = "w:/Drone_Follow/data/profiles"
