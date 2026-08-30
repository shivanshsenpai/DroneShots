"""
Target Profile Storage and Biometric Database.
Saves, loads, and manages registered multi-angle person profiles.
"""
import os
import json
import numpy as np
from typing import List, Dict, Any, Optional

from backend.config import ServerConfig


class ProfileStore:
    def __init__(self, storage_dir: str = ServerConfig.PROFILE_DIR):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self._ensure_default_profiles()

    def _ensure_default_profiles(self):
        """Creates initial demo profiles if folder is empty."""
        profiles = self.list_profiles()
        if not profiles:
            demo_profile = {
                "id": "target_alpha_demo",
                "name": "Commander (Demo)",
                "created_at": "2026-08-29 12:00:00",
                "orientation_at_scan": "FRONT",
                "face_detected": True,
                "face_embedding": [0.05 * np.sin(i) for i in range(128)],
                "proportions": {
                    "shoulder_to_hip_ratio": 1.15,
                    "torso_to_leg_ratio": 0.68,
                    "shoulder_to_height_ratio": 0.26,
                    "hip_to_height_ratio": 0.21,
                    "total_height_metric": 1.78,
                    "shoulder_width_metric": 0.44
                },
                "head_signature": [0.01] * 1152,
                "torso_signature": [0.01] * 1152,
                "legs_signature": [0.01] * 1152,
                "color_palette": {
                    "hair_hex": "#1E293B",
                    "torso_hex": "#00F0FF",
                    "legs_hex": "#0F172A"
                },
                "landmarks_3d_world": [
                    {"x": 0.0, "y": -0.6, "z": 0.0, "visibility": 0.99}, # Nose
                    {"x": -0.2, "y": -0.3, "z": 0.0, "visibility": 0.99}, # Left shoulder
                    {"x": 0.2, "y": -0.3, "z": 0.0, "visibility": 0.99},  # Right shoulder
                    {"x": -0.15, "y": 0.2, "z": 0.0, "visibility": 0.99}, # Left hip
                    {"x": 0.15, "y": 0.2, "z": 0.0, "visibility": 0.99},  # Right hip
                    {"x": -0.15, "y": 0.7, "z": 0.0, "visibility": 0.99}, # Left knee
                    {"x": 0.15, "y": 0.7, "z": 0.0, "visibility": 0.99},  # Right knee
                    {"x": -0.15, "y": 1.1, "z": 0.0, "visibility": 0.99}, # Left ankle
                    {"x": 0.15, "y": 1.1, "z": 0.0, "visibility": 0.99},  # Right ankle
                ],
                "bbox_area_ratio": 0.18,
                "center": [0.5, 0.45],
                "yaw_deg": 0.0,
                "pitch_deg": 0.0
            }
            self.save_profile(demo_profile)

    def save_profile(self, profile: Dict[str, Any]) -> str:
        """Saves a profile to disk as JSON."""
        pid = profile.get("id") or f"profile_{int(os.times().elapsed * 1000)}"
        file_path = os.path.join(self.storage_dir, f"{pid}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        return pid

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single profile by ID."""
        file_path = os.path.join(self.storage_dir, f"{profile_id}.json")
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def list_profiles(self) -> List[Dict[str, Any]]:
        """Returns a list of all saved profiles summary."""
        profiles = []
        if not os.path.exists(self.storage_dir):
            return profiles

        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.storage_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        profiles.append({
                            "id": data.get("id", fname.replace(".json", "")),
                            "name": data.get("name", "Unnamed Profile"),
                            "created_at": data.get("created_at", "N/A"),
                            "orientation": data.get("orientation_at_scan", "UNKNOWN"),
                            "color_palette": data.get("color_palette", {}),
                            "face_detected": data.get("face_detected", False)
                        })
                except Exception:
                    continue
        return profiles

    def delete_profile(self, profile_id: str) -> bool:
        """Deletes a profile from disk."""
        file_path = os.path.join(self.storage_dir, f"{profile_id}.json")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                return True
            except Exception:
                return False
        return False
