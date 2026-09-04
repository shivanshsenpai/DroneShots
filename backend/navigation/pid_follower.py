"""
4-Axis Smooth PID Follow Controller for DJI Ryze Tello.
Controls Yaw, Pitch, Throttle, and Roll velocities to keep the target tracked
from chosen perspective (Front Lead, Back Chase, Side Flank, Dynamic Orbit)
with dynamic setpoint tuning, velocity ramping, and track-loss reacquisition.
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
        self.target_distance_m: float = 2.0  # Desired distance in meters (1.0 to 5.0)
        self.target_altitude_m: float = 1.3  # Desired altitude in meters (0.5 to 2.5)

        # Dynamic PID gains (can be tuned live via API)
        self.kp_yaw = self.pid_cfg.KP_YAW
        self.ki_yaw = self.pid_cfg.KI_YAW
        self.kd_yaw = self.pid_cfg.KD_YAW

        self.kp_pitch = self.pid_cfg.KP_PITCH
        self.ki_pitch = self.pid_cfg.KI_PITCH
        self.kd_pitch = self.pid_cfg.KD_PITCH

        self.kp_throttle = self.pid_cfg.KP_THROTTLE
        self.ki_throttle = self.pid_cfg.KI_THROTTLE
        self.kd_throttle = self.pid_cfg.KD_THROTTLE

        self.kp_roll = self.pid_cfg.KP_ROLL
        self.ki_roll = self.pid_cfg.KI_ROLL
        self.kd_roll = self.pid_cfg.KD_ROLL

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
        self.last_target_seen_time = time.time()
        self.last_known_offset_x = 0.0
        
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

    def set_parameters(self, distance_m: Optional[float] = None, altitude_m: Optional[float] = None):
        """Live updates target distance and altitude setpoints."""
        if distance_m is not None:
            self.target_distance_m = float(np.clip(distance_m, 0.8, 5.0))
        if altitude_m is not None:
            self.target_altitude_m = float(np.clip(altitude_m, 0.5, 2.5))

    def update_gains(self, gains: Dict[str, float]):
        """Live updates PID gains."""
        if "kp_yaw" in gains: self.kp_yaw = float(gains["kp_yaw"])
        if "kd_yaw" in gains: self.kd_yaw = float(gains["kd_yaw"])
        if "kp_pitch" in gains: self.kp_pitch = float(gains["kp_pitch"])
        if "kd_pitch" in gains: self.kd_pitch = float(gains["kd_pitch"])
        if "kp_throttle" in gains: self.kp_throttle = float(gains["kp_throttle"])
        if "kd_throttle" in gains: self.kd_throttle = float(gains["kd_throttle"])

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

        target_detected = tracking_state.get("target_detected", False)
        target_matched = tracking_state.get("target_matched", False)

        # -------------------------------------------------------------
        # Target Lost & Search Maneuver Protocol
        # -------------------------------------------------------------
        if not target_detected or not target_matched:
            time_lost = now - self.last_target_seen_time
            # For the first 1.5 seconds of loss: maintain gentle predictive search in last direction
            if time_lost < 1.5 and abs(self.last_known_offset_x) > 0.1:
                search_yaw = int(np.sign(self.last_known_offset_x) * 18)
                return {"roll": 0, "pitch": 0, "throttle": 0, "yaw": search_yaw}
            # Otherwise hover stably in place
            self.reset()
            return {"roll": 0, "pitch": 0, "throttle": 0, "yaw": 0}

        self.last_target_seen_time = now
        offset_x = tracking_state.get("offset_x", 0.0)
        offset_y = tracking_state.get("offset_y", 0.0)
        self.last_known_offset_x = offset_x
        
        area_ratio = tracking_state.get("bbox_area_ratio", self.follow_cfg.DESIRED_TARGET_AREA)
        est_distance = tracking_state.get("estimated_distance_m", self.target_distance_m)

        # Compute dynamic desired bounding box area based on target_distance_m
        # e.g., 1.5m -> ~0.22 area, 2.0m -> ~0.15 area, 3.0m -> ~0.08 area
        desired_area = float(np.clip(0.60 / (self.target_distance_m ** 1.6), 0.04, 0.40))

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
            (self.kp_yaw * error_x * 100.0) +
            (self.ki_yaw * self.integral_x * 100.0) +
            (self.kd_yaw * derivative_x * 100.0)
        )

        # -------------------------------------------------------------
        # 2. THROTTLE AXIS (Vertical Height & Centering)
        # -------------------------------------------------------------
        # Target above center (offset_y < 0) -> drone moves UP (+ throttle)
        # Target below center (offset_y > 0) -> drone moves DOWN (- throttle)
        error_y = -offset_y
        if abs(error_y) < self.pid_cfg.DEADBAND_Y:
            error_y = 0.0

        self.integral_y = np.clip(self.integral_y + error_y * dt, -1.0, 1.0)
        derivative_y = (error_y - self.prev_error_y) / dt
        self.prev_error_y = error_y

        throttle_cmd = (
            (self.kp_throttle * error_y * 100.0) +
            (self.ki_throttle * self.integral_y * 100.0) +
            (self.kd_throttle * derivative_y * 100.0)
        )

        # -------------------------------------------------------------
        # 3. PITCH AXIS (Distance Tracking with Safety Backoff)
        # -------------------------------------------------------------
        error_dist = (desired_area - area_ratio) / (desired_area + 1e-6)
        if abs(error_dist) < self.pid_cfg.DEADBAND_AREA:
            error_dist = 0.0

        # Safety: Close-range collision backoff
        if area_ratio > self.follow_cfg.MIN_DISTANCE_AREA_LIMIT or est_distance < 0.9:
            error_dist = -1.3  # Strong backward safety push

        self.integral_dist = np.clip(self.integral_dist + error_dist * dt, -1.0, 1.0)
        derivative_dist = (error_dist - self.prev_error_dist) / dt
        self.prev_error_dist = error_dist

        pitch_cmd = (
            (self.kp_pitch * error_dist * 100.0) +
            (self.ki_pitch * self.integral_dist * 100.0) +
            (self.kd_pitch * derivative_dist * 100.0)
        )

        # -------------------------------------------------------------
        # 4. ROLL AXIS (Lateral Strafe & Orbit / Flank Follow)
        # -------------------------------------------------------------
        roll_cmd = 0.0
        if self.mode == "FLANK_LEFT":
            roll_cmd = -18.0
        elif self.mode == "FLANK_RIGHT":
            roll_cmd = 18.0
        elif self.mode == "ORBIT":
            roll_cmd = 22.0

        # -------------------------------------------------------------
        # 5. Output Velocity Smoothing & Gimbal-Like Damping
        # -------------------------------------------------------------
        alpha = 0.70  # Higher smoothing for cinematic motion
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
