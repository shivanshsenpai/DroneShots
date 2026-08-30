"""
MediaPipe 3D Pose Estimator and Skeletal Feature Extractor.
Extracts 33 3D world landmarks, 2D pixel coordinates, body orientation angle, and skeletal proportions.
"""
import cv2
import numpy as np
import mediapipe as mp
from typing import Optional, Dict, Any, Tuple, List


class PoseEstimator3D:
    def __init__(self, min_detection_confidence: float = 0.55, min_tracking_confidence: float = 0.55):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            enable_segmentation=True,
            smooth_segmentation=True,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles

    def process_frame(self, frame_bgr: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        Processes a BGR video frame and extracts 2D landmarks, 3D world landmarks,
        orientation classification, bounding boxes, and body proportions.
        """
        h, w, c = frame_bgr.shape
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.pose.process(frame_rgb)

        if not results.pose_landmarks or not results.pose_world_landmarks:
            return None

        landmarks_2d = results.pose_landmarks.landmark
        landmarks_3d = results.pose_world_landmarks.landmark

        # Extract 2D pixel points for key body parts
        points_2d = []
        xs, ys, zs, visibilities = [], [], [], []
        for lm in landmarks_2d:
            px, py = int(lm.x * w), int(lm.y * h)
            points_2d.append({
                "x": lm.x,
                "y": lm.y,
                "z": lm.z,
                "px": px,
                "py": py,
                "visibility": lm.visibility
            })
            if lm.visibility > 0.35:
                xs.append(px)
                ys.append(py)
                zs.append(lm.z)

        if not xs or not ys:
            return None

        # Calculate bounding box
        x_min, x_max = max(0, min(xs)), min(w - 1, max(xs))
        y_min, y_max = max(0, min(ys)), min(h - 1, max(ys))
        bbox_w = x_max - x_min
        bbox_h = y_max - y_min
        bbox_area_ratio = (bbox_w * bbox_h) / (w * h)

        # 3D World Landmarks array (metric coordinates centered at hips)
        points_3d_world = []
        for lm in landmarks_3d:
            points_3d_world.append({
                "x": float(lm.x),
                "y": float(lm.y),
                "z": float(lm.z),
                "visibility": float(lm.visibility)
            })

        # Calculate Orientation Angle and Classification
        orientation, yaw_deg, pitch_deg = self._estimate_orientation(landmarks_2d, landmarks_3d)

        # Extract Skeletal Proportion Vector (Invariant 3D proportions)
        proportions = self._calculate_skeletal_proportions(landmarks_3d)

        # Partition regions for Multi-Segment ReID
        segments = self._extract_body_segments(frame_bgr, landmarks_2d, w, h)

        return {
            "bbox": [int(x_min), int(y_min), int(bbox_w), int(bbox_h)],
            "bbox_normalized": [x_min / w, y_min / h, bbox_w / w, bbox_h / h],
            "bbox_area_ratio": float(bbox_area_ratio),
            "center": [float((x_min + bbox_w / 2) / w), float((y_min + bbox_h / 2) / h)],
            "orientation": orientation,
            "yaw_deg": float(yaw_deg),
            "pitch_deg": float(pitch_deg),
            "landmarks_2d": points_2d,
            "landmarks_3d_world": points_3d_world,
            "proportions": proportions,
            "segments": segments,
            "segmentation_mask": results.segmentation_mask
        }

    def _estimate_orientation(self, lm_2d, lm_3d) -> Tuple[str, float, float]:
        """
        Determines if the person is facing Front, Back, Left Side, Right Side, or Overhead.
        Uses 3D shoulder vectors and facial feature visibility (nose, eyes, ears).
        """
        # Shoulder 3D world coordinates
        l_shoulder = lm_3d[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value]
        r_shoulder = lm_3d[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
        
        # Facial landmarks visibility
        nose = lm_2d[self.mp_pose.PoseLandmark.NOSE.value]
        l_ear = lm_2d[self.mp_pose.PoseLandmark.LEFT_EAR.value]
        r_ear = lm_2d[self.mp_pose.PoseLandmark.RIGHT_EAR.value]

        # Shoulder delta in 3D (X and Z depth)
        dx = r_shoulder.x - l_shoulder.x
        dz = r_shoulder.z - l_shoulder.z

        # Calculate yaw in degrees (-180 to 180)
        yaw_rad = np.arctan2(dz, dx)
        yaw_deg = np.degrees(yaw_rad)

        # Pitch angle (up/down inclination)
        mid_shoulder_y = (l_shoulder.y + r_shoulder.y) / 2.0
        mid_hip_y = (lm_3d[self.mp_pose.PoseLandmark.LEFT_HIP.value].y + lm_3d[self.mp_pose.PoseLandmark.RIGHT_HIP.value].y) / 2.0
        pitch_deg = np.degrees(np.arctan2(mid_shoulder_y - mid_hip_y, 1.0))

        # Face visibility heuristic
        face_visible = (nose.visibility > 0.6) or (l_ear.visibility > 0.6 and r_ear.visibility > 0.6)
        
        # Classify orientation
        if abs(yaw_deg) < 30:
            if face_visible and nose.visibility > 0.5:
                orientation = "FRONT"
            else:
                orientation = "BACK"
        elif yaw_deg > 30 and yaw_deg < 140:
            orientation = "RIGHT_PROFILE"
        elif yaw_deg < -30 and yaw_deg > -140:
            orientation = "LEFT_PROFILE"
        else:
            orientation = "BACK"

        return orientation, yaw_deg, pitch_deg

    def _calculate_skeletal_proportions(self, lm_3d) -> Dict[str, float]:
        """
        Calculates metric-independent anatomical proportions (scale-invariant).
        """
        try:
            ls = np.array([lm_3d[11].x, lm_3d[11].y, lm_3d[11].z])
            rs = np.array([lm_3d[12].x, lm_3d[12].y, lm_3d[12].z])
            lh = np.array([lm_3d[23].x, lm_3d[23].y, lm_3d[23].z])
            rh = np.array([lm_3d[24].x, lm_3d[24].y, lm_3d[24].z])
            lk = np.array([lm_3d[25].x, lm_3d[25].y, lm_3d[25].z])
            rk = np.array([lm_3d[26].x, lm_3d[26].y, lm_3d[26].z])
            la = np.array([lm_3d[27].x, lm_3d[27].y, lm_3d[27].z])
            ra = np.array([lm_3d[28].x, lm_3d[28].y, lm_3d[28].z])

            shoulder_width = float(np.linalg.norm(ls - rs))
            hip_width = float(np.linalg.norm(lh - rh))
            torso_length = float(np.linalg.norm(((ls + rs) / 2.0) - ((lh + rh) / 2.0)))
            leg_length = float((np.linalg.norm(lh - lk) + np.linalg.norm(lk - la) + 
                               np.linalg.norm(rh - rk) + np.linalg.norm(rk - ra)) / 2.0)

            total_height_est = torso_length + leg_length + 0.25  # head estimate

            return {
                "shoulder_to_hip_ratio": float(shoulder_width / (hip_width + 1e-6)),
                "torso_to_leg_ratio": float(torso_length / (leg_length + 1e-6)),
                "shoulder_to_height_ratio": float(shoulder_width / (total_height_est + 1e-6)),
                "hip_to_height_ratio": float(hip_width / (total_height_est + 1e-6)),
                "total_height_metric": float(total_height_est),
                "shoulder_width_metric": float(shoulder_width)
            }
        except Exception:
            return {
                "shoulder_to_hip_ratio": 1.1,
                "torso_to_leg_ratio": 0.65,
                "shoulder_to_height_ratio": 0.25,
                "hip_to_height_ratio": 0.20,
                "total_height_metric": 1.70,
                "shoulder_width_metric": 0.42
            }

    def _extract_body_segments(self, frame_bgr: np.ndarray, lm_2d, w: int, h: int) -> Dict[str, Any]:
        """
        Crops key body segments (Head/Hair, Upper Torso, Lower Body) for appearance ReID.
        """
        segments = {}
        try:
            # 1. Head / Hair region
            nose = lm_2d[0]
            l_ear = lm_2d[7]
            r_ear = lm_2d[8]
            head_cx = int(nose.x * w)
            head_cy = int(nose.y * h)
            head_rad = int(max(abs(l_ear.x - r_ear.x) * w * 1.3, 30))
            
            hx1 = max(0, head_cx - head_rad)
            hy1 = max(0, head_cy - int(head_rad * 1.4))
            hx2 = min(w, head_cx + head_rad)
            hy2 = min(h, head_cy + int(head_rad * 0.8))
            
            if hx2 > hx1 and hy2 > hy1:
                segments["head_crop"] = frame_bgr[hy1:hy2, hx1:hx2]
                segments["head_box"] = [hx1, hy1, hx2 - hx1, hy2 - hy1]

            # 2. Upper Torso region (between shoulders and hips)
            ls = lm_2d[11]
            rs = lm_2d[12]
            lh = lm_2d[23]
            rh = lm_2d[24]

            tx1 = max(0, int(min(ls.x, rs.x, lh.x, rh.x) * w))
            tx2 = min(w, int(max(ls.x, rs.x, lh.x, rh.x) * w))
            ty1 = max(0, int(min(ls.y, rs.y) * h))
            ty2 = min(h, int(max(lh.y, rh.y) * h))

            if tx2 > tx1 and ty2 > ty1:
                segments["torso_crop"] = frame_bgr[ty1:ty2, tx1:tx2]
                segments["torso_box"] = [tx1, ty1, tx2 - tx1, ty2 - ty1]

            # 3. Lower Torso / Legs region
            lk = lm_2d[25]
            rk = lm_2d[26]
            la = lm_2d[27]
            ra = lm_2d[28]

            lx1 = max(0, int(min(lh.x, rh.x, lk.x, rk.x, la.x, ra.x) * w))
            lx2 = min(w, int(max(lh.x, rh.x, lk.x, rk.x, la.x, ra.x) * w))
            ly1 = max(0, int(min(lh.y, rh.y) * h))
            ly2 = min(h, int(max(la.y, ra.y, lk.y, rk.y) * h))

            if lx2 > lx1 and ly2 > ly1:
                segments["legs_crop"] = frame_bgr[ly1:ly2, lx1:lx2]
                segments["legs_box"] = [lx1, ly1, lx2 - lx1, ly2 - lx1]
        except Exception as e:
            pass

        return segments
