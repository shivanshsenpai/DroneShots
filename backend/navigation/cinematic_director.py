"""
Cinematic QuickShot Flight Director for DJI Ryze Tello.
Choreographs automated movie-grade flight routines:
- DRONIE: Backs away & ascends at 45 degrees, then returns to origin.
- ROCKET: Ascends vertically while maintaining subject lock.
- HELIX: Upward spiral orbit around target with expanding radius.
- BOOMERANG: Sweeping oval path swinging wide and returning to start.
Includes velocity ramping, boundary safeguards, and return-to-base completion.
"""
import time
import numpy as np
from typing import Dict, Any, Tuple, Optional


class CinematicDirector:
    def __init__(self):
        self.is_active: bool = False
        self.current_maneuver: Optional[str] = None
        self.start_time: float = 0.0
        self.phase: str = "IDLE"  # "APPROACH", "EXECUTE", "RETURN", "DONE"
        self.total_duration: float = 6.0
        self.progress_pct: float = 0.0

        # Snapshot of initial telemetry at trigger
        self.init_altitude_m: float = 1.2
        self.init_distance_m: float = 2.0

        # Output RC smooth filter
        self.curr_roll: float = 0.0
        self.curr_pitch: float = 0.0
        self.curr_throttle: float = 0.0
        self.curr_yaw: float = 0.0

    def start_maneuver(self, maneuver: str, current_telemetry: Dict[str, Any], current_tracking: Dict[str, Any]) -> bool:
        """Starts a cinematic flight choreography routine."""
        maneuver_upper = maneuver.upper()
        valid = ["DRONIE", "ROCKET", "HELIX", "BOOMERANG"]
        if maneuver_upper not in valid:
            return False

        self.current_maneuver = maneuver_upper
        self.is_active = True
        self.start_time = time.time()
        self.phase = "EXECUTE"
        self.progress_pct = 0.0

        # Durations tailored for each maneuver
        durations = {
            "DRONIE": 6.5,
            "ROCKET": 5.0,
            "HELIX": 8.0,
            "BOOMERANG": 7.5
        }
        self.total_duration = durations.get(maneuver_upper, 6.0)

        alt_cm = current_telemetry.get("altitude_cm", 120) or 120
        self.init_altitude_m = max(0.5, alt_cm / 100.0)
        self.init_distance_m = current_tracking.get("estimated_distance_m", 2.0) or 2.0

        self.curr_roll = 0.0
        self.curr_pitch = 0.0
        self.curr_throttle = 0.0
        self.curr_yaw = 0.0

        print(f"[CINEMATIC] Started QuickShot: {self.current_maneuver} (Duration: {self.total_duration}s)")
        return True

    def abort(self):
        """Immediately aborts any active cinematic routine."""
        if self.is_active:
            print(f"[CINEMATIC] Aborted QuickShot: {self.current_maneuver}")
        self.is_active = False
        self.current_maneuver = None
        self.phase = "IDLE"
        self.progress_pct = 0.0
        self.curr_roll = 0.0
        self.curr_pitch = 0.0
        self.curr_throttle = 0.0
        self.curr_yaw = 0.0

    def get_status(self) -> Dict[str, Any]:
        """Returns current cinematic director state."""
        return {
            "active": self.is_active,
            "maneuver": self.current_maneuver or "NONE",
            "phase": self.phase,
            "progress_pct": round(self.progress_pct, 1),
            "time_elapsed": round(time.time() - self.start_time, 1) if self.is_active else 0.0,
            "duration_total": self.total_duration
        }

    def compute_rc_commands(
        self,
        dt: float,
        current_telemetry: Dict[str, Any],
        current_tracking: Dict[str, Any]
    ) -> Tuple[Dict[str, int], Dict[str, Any]]:
        """
        Computes 4-axis RC commands (-100 to +100) for the active cinematic choreography.
        """
        if not self.is_active or not self.current_maneuver:
            return {"roll": 0, "pitch": 0, "throttle": 0, "yaw": 0}, self.get_status()

        elapsed = time.time() - self.start_time
        t_norm = min(1.0, elapsed / self.total_duration)
        self.progress_pct = t_norm * 100.0

        # Check completion
        if t_norm >= 1.0:
            print(f"[CINEMATIC] Completed QuickShot: {self.current_maneuver}")
            self.abort()
            return {"roll": 0, "pitch": 0, "throttle": 0, "yaw": 0}, self.get_status()

        target_roll = 0.0
        target_pitch = 0.0
        target_throttle = 0.0
        target_yaw = 0.0

        # Target centering error from tracking (to keep subject in frame during maneuver)
        cx_offset = current_tracking.get("offset_x", 0.0) if current_tracking.get("target_detected") else 0.0
        # Corrective yaw bias to keep target centered
        yaw_centering = float(np.clip(cx_offset * 65.0, -25.0, 25.0))

        # -------------------------------------------------------------
        # 1. DRONIE (Fly backwards & climb at 45 degrees, then return)
        # -------------------------------------------------------------
        if self.current_maneuver == "DRONIE":
            # Phase 1: Outward ascent (0.0 to 0.6)
            # Phase 2: Gentle return (0.6 to 1.0)
            if t_norm < 0.60:
                self.phase = "EXPANDING"
                ease = np.sin((t_norm / 0.60) * (np.pi / 2.0))
                target_pitch = -28.0 * (1.0 - 0.2 * ease) # Backwards
                target_throttle = 30.0 * (1.0 - 0.2 * ease) # Upwards
            else:
                self.phase = "RETURNING"
                ret_norm = (t_norm - 0.60) / 0.40
                ease_ret = np.sin(ret_norm * (np.pi / 2.0))
                target_pitch = 22.0 * (1.0 - ease_ret) # Forward back to origin
                target_throttle = -24.0 * (1.0 - ease_ret) # Descend back to origin

            target_yaw = yaw_centering

        # -------------------------------------------------------------
        # 2. ROCKET (Vertical ascent while locking camera down on subject)
        # -------------------------------------------------------------
        elif self.current_maneuver == "ROCKET":
            if t_norm < 0.55:
                self.phase = "ASCENDING"
                target_throttle = 40.0
                target_pitch = 0.0
            else:
                self.phase = "DESCENDING"
                ret_norm = (t_norm - 0.55) / 0.45
                target_throttle = -30.0 * (1.0 - ret_norm)
                target_pitch = 0.0

            target_yaw = yaw_centering

        # -------------------------------------------------------------
        # 3. HELIX (Upward spiral orbit with expanding radius)
        # -------------------------------------------------------------
        elif self.current_maneuver == "HELIX":
            self.phase = "SPIRALING"
            # Simultaneous lateral roll (orbit) + continuous yaw turn + vertical throttle climb
            orbit_speed = 26.0 + 8.0 * t_norm # Roll lateral
            yaw_spin = 24.0 + 6.0 * t_norm    # Yaw rotation
            throttle_climb = 22.0 * (1.0 - t_norm * 0.4) # Climbing upwards

            target_roll = orbit_speed
            target_yaw = yaw_spin + yaw_centering * 0.5
            target_throttle = throttle_climb
            target_pitch = -10.0 * t_norm # Expand radius backwards

        # -------------------------------------------------------------
        # 4. BOOMERANG (Sweeping oval path around subject)
        # -------------------------------------------------------------
        elif self.current_maneuver == "BOOMERANG":
            angle = t_norm * 2.0 * np.pi
            self.phase = "ORBITING"
            # Elliptical trajectory: roll = cos(angle), pitch = sin(angle)
            target_roll = float(np.sin(angle) * 32.0)
            target_pitch = float(-np.cos(angle) * 25.0)
            target_throttle = float(np.sin(angle * 0.5) * 15.0) # Gentle undulation
            target_yaw = yaw_centering + float(np.cos(angle) * 14.0)

        # Smooth ramping filter (avoid sudden motor shocks)
        alpha = 0.75
        self.curr_roll = alpha * self.curr_roll + (1.0 - alpha) * target_roll
        self.curr_pitch = alpha * self.curr_pitch + (1.0 - alpha) * target_pitch
        self.curr_throttle = alpha * self.curr_throttle + (1.0 - alpha) * target_throttle
        self.curr_yaw = alpha * self.curr_yaw + (1.0 - alpha) * target_yaw

        rc_out = {
            "roll": int(np.clip(self.curr_roll, -45, 45)),
            "pitch": int(np.clip(self.curr_pitch, -45, 45)),
            "throttle": int(np.clip(self.curr_throttle, -45, 45)),
            "yaw": int(np.clip(self.curr_yaw, -45, 45))
        }

        return rc_out, self.get_status()
