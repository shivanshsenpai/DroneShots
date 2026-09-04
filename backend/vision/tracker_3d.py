"""
Unified 3D Multi-Angle Target Tracking Engine.
Fuses 3D Pose, Facial Biometrics, and Multi-Segment Appearance ReID with
Centroid Velocity Estimation, Trajectory Breadcrumbs, and Continuous Profile Learning.
"""
import time
import cv2
import numpy as np
from typing import Optional, Dict, Any, Tuple, List

from backend.vision.pose_estimator import PoseEstimator3D
from backend.vision.face_reid import FaceBiometricsEngine
from backend.vision.appearance_reid import AppearanceReID
from backend.config import VisionConfig


class UnifiedTracker3D:
    def __init__(self, config: Optional[VisionConfig] = None):
        self.config = config or VisionConfig()
        self.pose_estimator = PoseEstimator3D(
            min_detection_confidence=self.config.MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=self.config.MIN_TRACKING_CONFIDENCE
        )
        self.face_engine = FaceBiometricsEngine()
        self.appearance_reid = AppearanceReID()

        # Currently locked target profile
        self.locked_profile: Optional[Dict[str, Any]] = None
        self.is_locked: bool = False
        self.last_seen_timestamp: float = 0.0
        self.lock_confidence: float = 0.0

        # Trajectory & Velocity Tracking
        self.prev_centroid: Optional[Tuple[float, float, float]] = None  # (cx, cy, timestamp)
        self.target_velocity_px_s: Tuple[float, float] = (0.0, 0.0)      # (vx, vy) in screen ratio per second
        self.target_speed_mps: float = 0.0                              # estimated target real-world speed m/s
        self.trajectory_breadcrumbs: List[Dict[str, float]] = []        # list of {x, y, t}

    def set_locked_target(self, profile: Optional[Dict[str, Any]]) -> None:
        """Sets or clears the active target profile to follow."""
        self.locked_profile = profile
        self.is_locked = profile is not None
        if not self.is_locked:
            self.lock_confidence = 0.0
        self.trajectory_breadcrumbs.clear()
        self.prev_centroid = None
        self.target_velocity_px_s = (0.0, 0.0)
        self.target_speed_mps = 0.0

    def generate_scan_profile(self, frame_bgr: np.ndarray, name: str = "Subject Alpha") -> Optional[Dict[str, Any]]:
        """
        Executes full 360° feature extraction on the current subject in frame.
        Used during the Scan & Register flow.
        """
        pose_data = self.pose_estimator.process_frame(frame_bgr)
        if not pose_data:
            return None

        segments = pose_data["segments"]
        face_data = self.face_engine.extract_face_embedding(frame_bgr, segments.get("head_crop"))
        appearance_data = self.appearance_reid.extract_appearance_profile(segments)

        profile = {
            "id": f"target_{int(time.time() * 1000)}",
            "name": name,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "orientation_at_scan": pose_data["orientation"],
            "face_embedding": face_data["embedding"] if face_data else None,
            "face_detected": face_data is not None,
            "proportions": pose_data["proportions"],
            "head_signature": appearance_data["head_signature"],
            "torso_signature": appearance_data["torso_signature"],
            "legs_signature": appearance_data["legs_signature"],
            "color_palette": appearance_data["color_palette"],
            "landmarks_3d_world": pose_data["landmarks_3d_world"],
            "bbox_area_ratio": pose_data["bbox_area_ratio"],
            "center": pose_data["center"],
            "yaw_deg": pose_data["yaw_deg"],
            "pitch_deg": pose_data["pitch_deg"]
        }

        return profile

    def process_and_track(self, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Processes the live drone frame:
        1. Estimates 3D pose & orientation.
        2. If target is locked, evaluates multi-angle match confidence.
        3. Computes target center offset (dx, dy), estimated metric distance, velocity, and breadcrumbs.
        """
        h, w, c = frame_bgr.shape
        now = time.time()

        pose_data = self.pose_estimator.process_frame(frame_bgr)

        result: Dict[str, Any] = {
            "target_detected": False,
            "target_matched": False,
            "confidence": 0.0,
            "orientation": "UNKNOWN",
            "yaw_deg": 0.0,
            "pitch_deg": 0.0,
            "bbox": None,
            "bbox_normalized": None,
            "bbox_area_ratio": 0.0,
            "center": [0.5, 0.5],
            "offset_x": 0.0,
            "offset_y": 0.0,
            "estimated_distance_m": 0.0,
            "landmarks_3d_world": None,
            "landmarks_2d": None,
            "color_palette": None,
            "is_locked": self.is_locked,
            "time_since_last_seen": now - self.last_seen_timestamp if self.last_seen_timestamp > 0 else 999.0,
            "velocity": {"vx": 0.0, "vy": 0.0, "speed_mps": 0.0},
            "trajectory": []
        }

        if not pose_data:
            return result

        result["target_detected"] = True
        result["orientation"] = pose_data["orientation"]
        result["yaw_deg"] = pose_data["yaw_deg"]
        result["pitch_deg"] = pose_data["pitch_deg"]
        result["bbox"] = pose_data["bbox"]
        result["bbox_normalized"] = pose_data["bbox_normalized"]
        result["bbox_area_ratio"] = pose_data["bbox_area_ratio"]
        result["center"] = pose_data["center"]
        result["landmarks_3d_world"] = pose_data["landmarks_3d_world"]
        result["landmarks_2d"] = pose_data["landmarks_2d"]

        # Calculate offsets from center (0.5, 0.45)
        cx, cy = pose_data["center"]
        result["offset_x"] = float(cx - 0.50)
        result["offset_y"] = float(cy - 0.45)

        # Estimate distance in meters using vertical height ratio & focal heuristic
        bbox_h_px = max(10, pose_data["bbox"][3])
        estimated_dist = (1.70 * 650.0) / (bbox_h_px + 1e-6)
        dist_m = float(np.clip(estimated_dist, 0.4, 8.0))
        result["estimated_distance_m"] = dist_m

        # Compute Velocity & Trajectory Breadcrumbs
        if self.prev_centroid is not None:
            pcx, pcy, pt = self.prev_centroid
            dt = max(0.001, now - pt)
            vx = (cx - pcx) / dt
            vy = (cy - pcy) / dt
            # Smooth velocity filter
            alpha = 0.6
            self.target_velocity_px_s = (
                alpha * self.target_velocity_px_s[0] + (1 - alpha) * vx,
                alpha * self.target_velocity_px_s[1] + (1 - alpha) * vy
            )
            # Estimate metric speed in m/s (using distance & horizontal field of view)
            fov_width_m = 2.0 * dist_m * np.tan(np.radians(82.6 / 2.0))
            metric_speed = np.sqrt((vx * fov_width_m)**2 + (vy * fov_width_m * 0.75)**2)
            self.target_speed_mps = float(np.clip(metric_speed, 0.0, 10.0))

        self.prev_centroid = (cx, cy, now)

        # Update rolling trajectory breadcrumbs (keep max 18 points)
        self.trajectory_breadcrumbs.append({"x": cx, "y": cy, "t": now})
        if len(self.trajectory_breadcrumbs) > 18:
            self.trajectory_breadcrumbs.pop(0)

        result["velocity"] = {
            "vx": float(round(self.target_velocity_px_s[0], 3)),
            "vy": float(round(self.target_velocity_px_s[1], 3)),
            "speed_mps": float(round(self.target_speed_mps, 2))
        }
        result["trajectory"] = [{"x": p["x"], "y": p["y"]} for p in self.trajectory_breadcrumbs]

        # Extract current appearance and face
        segments = pose_data["segments"]
        current_appearance = self.appearance_reid.extract_appearance_profile(segments)
        result["color_palette"] = current_appearance["color_palette"]

        # If a target is currently locked, match against registered profile
        if self.is_locked and self.locked_profile:
            match_score = self._compute_multi_angle_match(
                frame_bgr, pose_data, current_appearance, segments, self.locked_profile
            )
            result["confidence"] = float(match_score)

            if match_score >= self.config.COMBINED_LOCK_THRESHOLD:
                result["target_matched"] = True
                self.last_seen_timestamp = now
                self.lock_confidence = match_score

                # Continuous Profile Refinement:
                # If high confidence (> 0.88), gently update appearance profile to adapt to lighting changes
                if match_score > 0.88 and current_appearance.get("torso_signature"):
                    self._enrich_profile(current_appearance)
            else:
                result["target_matched"] = False
        else:
            result["target_matched"] = True
            result["confidence"] = 0.85
            self.last_seen_timestamp = now

        return result

    def _enrich_profile(self, current_app: Dict[str, Any]):
        """Gently adapts registered color signature to lighting fluctuations."""
        try:
            if not self.locked_profile or not current_app: return
            alpha = 0.95  # Retain 95% of original, 5% of current
            if "torso_signature" in self.locked_profile and current_app.get("torso_signature"):
                t_old = np.array(self.locked_profile["torso_signature"])
                t_new = np.array(current_app["torso_signature"])
                t_fused = (alpha * t_old + (1 - alpha) * t_new)
                self.locked_profile["torso_signature"] = t_fused.tolist()
        except Exception:
            pass

    def _compute_multi_angle_match(
        self,
        frame_bgr: np.ndarray,
        pose_data: Dict[str, Any],
        current_appearance: Dict[str, Any],
        segments: Dict[str, Any],
        registered: Dict[str, Any]
    ) -> float:
        """
        Computes an adaptive multi-angle score depending on whether the subject is
        facing FRONT, BACK, SIDE, or OVERHEAD.
        """
        orientation = pose_data["orientation"]

        # 1. Appearance ReID score (torso, legs, hair)
        appearance_score = self.appearance_reid.match_appearance(current_appearance, registered)

        # 2. Skeletal Proportions similarity
        prop_score = self._compare_proportions(pose_data["proportions"], registered.get("proportions", {}))

        # 3. Facial Biometrics score (if face visible)
        face_score = 0.0
        face_evaluated = False
        if orientation in ["FRONT", "LEFT_PROFILE", "RIGHT_PROFILE"] and registered.get("face_embedding"):
            current_face = self.face_engine.extract_face_embedding(frame_bgr, segments.get("head_crop"))
            if current_face and current_face.get("embedding"):
                face_score = self.face_engine.compare_embeddings(
                    current_face["embedding"], registered["face_embedding"]
                )
                face_evaluated = True

        # Adaptive multi-angle weighting
        if face_evaluated and face_score > 0.4:
            total_score = (0.35 * face_score) + (0.45 * appearance_score) + (0.20 * prop_score)
        elif orientation == "BACK":
            total_score = (0.70 * appearance_score) + (0.30 * prop_score)
        else:
            total_score = (0.60 * appearance_score) + (0.40 * prop_score)

        return float(np.clip(total_score, 0.0, 1.0))

    def _compare_proportions(self, current_props: Dict[str, float], reg_props: Dict[str, float]) -> float:
        """Compares scale-invariant skeletal proportions (0.0 to 1.0)."""
        if not reg_props:
            return 0.70

        diffs = []
        for key in ["shoulder_to_hip_ratio", "torso_to_leg_ratio", "shoulder_to_height_ratio"]:
            if key in current_props and key in reg_props:
                c_val = current_props[key]
                r_val = reg_props[key]
                rel_diff = abs(c_val - r_val) / (r_val + 1e-6)
                diffs.append(max(0.0, 1.0 - rel_diff * 1.5))

        return float(np.mean(diffs)) if diffs else 0.70
