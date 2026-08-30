"""
4-Axis Smooth PID Follow Controller for DJI Ryze Tello.
Controls Yaw, Pitch, Throttle, and Roll velocities to keep the target tracked
from chosen perspective (Front Lead, Back Chase, Side Flank, Dynamic Orbit).
"""
import time
import numpy as np
from typing import Dict, Any, Tuple, Optional

from backend.config import PIDConfig, FollowConfig


class PIDController4Axis:
    def __init__(self, pid_config: Optional[PIDConfig] = None, follow_config: Optional[FollowConfig] = None):
        self.pid_cfg = pid_config or PIDConfig()
        self.follow_cfg = follow_config or FollowConfig()

        # Follow Mode: "LEAD", "CHASE", "FLANK_LEFT", "FLANK_RIGHT", "ORBIT"
        self.mode = self.follow_cfg.DEFAULT_MODE
        self.target_distance_m: float = 2.0  # Desired distance in meters

        # Error tracking
        self.prev_error_x = 0.0
        self.prev_error_y = 0.0
        self.prev_error_dist = 0.0
        self.prev_error_roll = 0.0

        self.integral_x = 0.0
        self.integral_y = 0.0
        self.integral_dist = 0.0
        self.integral_roll = 0.0

        self.last_time = time.time()
        
        # Smoothed velocities
        self.curr_yaw = 0.0
        self.curr_pitch = 0.0
        self.curr_throttle = 0.0
        self.curr_roll = 0.0

    def set_mode(self, mode: str):
        """Sets follow mode ('LEAD', 'CHASE', 'FLANK_LEFT', 'FLANK_RIGHT', 'ORBIT')."""
        valid_modes = ["LEAD", "CHASE", "FLANK_LEFT", "FLANK_RIGHT", "ORBIT"]
        if mode.upper() in valid_modes:
            self.mode = mode.upper()
            self.reset()

    def reset(self):
        """Resets integral terms and velocity history."""
        self.prev_error_x = 0.0
        self.prev_error_y = 0.0
        self.prev_error_dist = 0.0
        self.prev_error_roll = 0.0
        self.integral_x = 0.0
        self.integral_y = 0.0
        self.integral_dist = 0.0
        self.integral_roll = 0.0
        self.curr_yaw = 0.0
        self.curr_pitch = 0.0
        self.curr_throttle = 0.0
        self.curr_roll = 0.0
        self.last_time = time.time()

    def compute_rc_velocities(self, tracking_state: Dict[str, Any]) -> Dict[str, int]:
        """
        Computes 4-axis RC commands (-100 to +100) based on target tracking state.
        Returns: {"roll": int, "pitch": int, "throttle": int, "yaw": int}
        """
        now = time.time()
        dt = max(0.01, min(0.2, now - self.last_time))
        self.last_time = now

        # If target not matched or lost, return zero velocity (hover safely)
        if not tracking_state.get("target_matched") or not tracking_state.get("target_detected"):
            self.reset()
            return {"roll": 0, "pitch": 0, "throttle": 0, "yaw": 0}

        # Target center offsets
        # offset_x: -0.5 (left) to +0.5 (right)
        # offset_y: -0.5 (top) to +0.5 (bottom)
        offset_x = tracking_state.get("offset_x", 0.0)
        offset_y = tracking_state.get("offset_y", 0.0)
        area_ratio = tracking_state.get("bbox_area_ratio", self.follow_cfg.DESIRED_TARGET_AREA)
        est_distance = tracking_state.get("estimated_distance_m", 2.0)

        # -------------------------------------------------------------
        # 1. YAW AXIS (Horizontal Centering)
        # -------------------------------------------------------------
        error_x = offset_x
        if abs(error_x) < self.pid_cfg.DEADBAND_X:
            error_x = 0.0

        self.integral_x = np.clip(self.integral_x + error_x * dt, -1.0, 1.0)
        derivative_x = (error_x - self.prev_error_x) / dt
        self.prev_error_x = error_x

        yaw_cmd = (
            (self.pid_cfg.KP_YAW * error_x * 100.0) +
            (self.pid_cfg.KI_YAW * self.integral_x * 100.0) +
            (self.pid_cfg.KD_YAW * derivative_x * 100.0)
        )

        # -------------------------------------------------------------
        # 2. THROTTLE AXIS (Vertical Height Centering)
        # -------------------------------------------------------------
        # Target above center (offset_y < 0) -> drone should move UP (+ throttle)
        # Target below center (offset_y > 0) -> drone should move DOWN (- throttle)
        error_y = -offset_y
        if abs(error_y) < self.pid_cfg.DEADBAND_Y:
            error_y = 0.0

        self.integral_y = np.clip(self.integral_y + error_y * dt, -1.0, 1.0)
        derivative_y = (error_y - self.prev_error_y) / dt
        self.prev_error_y = error_y

        throttle_cmd = (
            (self.pid_cfg.KP_THROTTLE * error_y * 100.0) +
            (self.pid_cfg.KI_THROTTLE * self.integral_y * 100.0) +
            (self.pid_cfg.KD_THROTTLE * derivative_y * 100.0)
        )

        # -------------------------------------------------------------
        # 3. PITCH AXIS (Distance / Forward-Backward Follow)
        # -------------------------------------------------------------
        # Area smaller than desired -> Target is far away -> Move FORWARD (+ pitch)
        # Area larger than desired -> Target is too close -> Move BACKWARD (- pitch)
        error_dist = (self.follow_cfg.DESIRED_TARGET_AREA - area_ratio) / self.follow_cfg.DESIRED_TARGET_AREA
        if abs(error_dist) < self.pid_cfg.DEADBAND_AREA:
            error_dist = 0.0

        # Safety: Close-range collision backoff
        if area_ratio > self.follow_cfg.MIN_DISTANCE_AREA_LIMIT:
            error_dist = -1.2  # Strong backward push

        self.integral_dist = np.clip(self.integral_dist + error_dist * dt, -1.0, 1.0)
        derivative_dist = (error_dist - self.prev_error_dist) / dt
        self.prev_error_dist = error_dist

        pitch_cmd = (
            (self.pid_cfg.KP_PITCH * error_dist * 100.0) +
            (self.pid_cfg.KI_PITCH * self.integral_dist * 100.0) +
            (self.pid_cfg.KD_PITCH * derivative_dist * 100.0)
        )

        # -------------------------------------------------------------
        # 4. ROLL AXIS (Lateral Strafe & Orbit / Flank Follow)
        # -------------------------------------------------------------
        roll_cmd = 0.0
        if self.mode == "FLANK_LEFT":
            roll_cmd = -18.0  # Constant left strafe while yawing to flank
        elif self.mode == "FLANK_RIGHT":
            roll_cmd = 18.0   # Constant right strafe
        elif self.mode == "ORBIT":
            roll_cmd = 22.0   # Smooth circular orbit around target

        # -------------------------------------------------------------
        # 5. Output Velocity Smoothing & Clamping
        # -------------------------------------------------------------
        alpha = 0.65  # Smoothing factor
        self.curr_yaw = alpha * self.curr_yaw + (1.0 - alpha) * yaw_cmd
        self.curr_pitch = alpha * self.curr_pitch + (1.0 - alpha) * pitch_cmd
        self.curr_throttle = alpha * self.curr_throttle + (1.0 - alpha) * throttle_cmd
        self.curr_roll = alpha * self.curr_roll + (1.0 - alpha) * roll_cmd

        # Clamp within maximum safe velocities
        final_yaw = int(np.clip(self.curr_yaw, -self.pid_cfg.MAX_SPEED_YAW, self.pid_cfg.MAX_SPEED_YAW))
        final_pitch = int(np.clip(self.curr_pitch, -self.pid_cfg.MAX_SPEED_PITCH, self.pid_cfg.MAX_SPEED_PITCH))
        final_throttle = int(np.clip(self.curr_throttle, -self.pid_cfg.MAX_SPEED_THROTTLE, self.pid_cfg.MAX_SPEED_THROTTLE))
        final_roll = int(np.clip(self.curr_roll, -self.pid_cfg.MAX_SPEED_ROLL, self.pid_cfg.MAX_SPEED_ROLL))

        return {
            "roll": final_roll,
            "pitch": final_pitch,
            "throttle": final_throttle,
            "yaw": final_yaw
        }
