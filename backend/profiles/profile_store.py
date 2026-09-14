"""
Target Profile Storage and Biometric Database.
Saves, loads, and manages registered multi-angle person profiles with atomic file replacement,
schema validation, thread safety, and point-in-time profile snapshot backups.
"""
import os
import time
import json
import shutil
import threading
import logging
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional

from backend.config import ServerConfig

logger = logging.getLogger("ProfileStore")


class ProfileStore:
    def __init__(self, storage_dir: str = ServerConfig.PROFILE_DIR):
        self._lock = threading.RLock()
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        
        self.backup_dir = os.path.join(os.path.dirname(self.storage_dir), "backups", "profiles")
        os.makedirs(self.backup_dir, exist_ok=True)
        
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

    def validate_profile(self, profile: Dict[str, Any]) -> bool:
        """Validates that a profile contains required fields and valid schema."""
        if not isinstance(profile, dict):
            return False
        if not profile.get("name") or not isinstance(profile.get("name"), str):
            return False
        # Optional orientation check
        valid_orients = {"FRONT", "SIDE_LEFT", "SIDE_RIGHT", "BACK", "OVERHEAD", "UNKNOWN"}
        orient = profile.get("orientation_at_scan", "FRONT")
        if orient not in valid_orients:
            profile["orientation_at_scan"] = "FRONT"
        return True

    def save_profile(self, profile: Dict[str, Any]) -> str:
        """
        Saves a profile to disk atomically via temporary file and atomic rename (os.replace).
        Guarantees Atomicity & Durability even in case of sudden process crash.
        """
        with self._lock:
            self.validate_profile(profile)

            pid = profile.get("id") or f"profile_{int(time.time() * 1000)}"
            profile["id"] = pid
            if "created_at" not in profile:
                profile["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            file_path = os.path.join(self.storage_dir, f"{pid}.json")
            temp_path = os.path.join(self.storage_dir, f"{pid}.tmp")

            # 1. Write to temp file
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2)
                f.flush()
                os.fsync(f.fileno())  # Ensure bytes hit disk

            # 2. Atomic rename / swap
            os.replace(temp_path, file_path)
            logger.info(f"[PROFILE_STORE] Saved profile atomically: {profile.get('name')} ({pid})")
            return pid

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single profile by ID."""
        with self._lock:
            file_path = os.path.join(self.storage_dir, f"{profile_id}.json")
            if not os.path.exists(file_path):
                return None
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[PROFILE_STORE] Error reading profile {profile_id}: {e}")
                return None

    def list_profiles(self) -> List[Dict[str, Any]]:
        """Returns a list of all saved profiles summary."""
        with self._lock:
            profiles = []
            if not os.path.exists(self.storage_dir):
                return profiles

            for fname in os.listdir(self.storage_dir):
                if fname.endswith(".json") and not fname.endswith(".tmp"):
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
        """Deletes a profile from disk with thread safety."""
        with self._lock:
            file_path = os.path.join(self.storage_dir, f"{profile_id}.json")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"[PROFILE_STORE] Deleted profile: {profile_id}")
                    return True
                except Exception as e:
                    logger.error(f"[PROFILE_STORE] Failed to delete profile {profile_id}: {e}")
                    return False
            return False

    def backup_profiles(self) -> Dict[str, Any]:
        """Creates a timestamped snapshot backup of all profiles."""
        with self._lock:
            os.makedirs(self.backup_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            snap_dir = os.path.join(self.backup_dir, f"profiles_backup_{ts}")
            os.makedirs(snap_dir, exist_ok=True)

            count = 0
            for fname in os.listdir(self.storage_dir):
                if fname.endswith(".json"):
                    src = os.path.join(self.storage_dir, fname)
                    dst = os.path.join(snap_dir, fname)
                    shutil.copy2(src, dst)
                    count += 1

            return {
                "backup_dir": snap_dir,
                "timestamp": ts,
                "profiles_backed_up": count
            }
