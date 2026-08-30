"""
Multi-Segment Appearance Re-Identification (ReID) Engine.
Computes multi-region HSV histograms (Hair/Head, Torso, Legs) and dominant color palettes
to enable tracking from any angle (Front, Back, Side, Overhead).
"""
import cv2
import numpy as np
from typing import Dict, Any, List, Optional, Tuple


class AppearanceReID:
    def __init__(self):
        # 3D HSV histogram bin resolutions
        self.h_bins = 18
        self.s_bins = 8
        self.v_bins = 8

    def extract_appearance_profile(self, segments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts appearance signatures for Head/Hair, Upper Torso, and Legs.
        """
        profile = {
            "head_signature": None,
            "torso_signature": None,
            "legs_signature": None,
            "color_palette": {
                "hair_hex": "#2B2B2B",
                "torso_hex": "#3B82F6",
                "legs_hex": "#1E293B"
            }
        }

        # 1. Head / Hair signature
        if "head_crop" in segments and segments["head_crop"] is not None and segments["head_crop"].size > 0:
            head_crop = segments["head_crop"]
            # Top half of head is predominantly hair/scalp
            hh, hw, _ = head_crop.shape
            hair_region = head_crop[0:int(hh * 0.5), :]
            if hair_region.size > 0:
                profile["head_signature"] = self._compute_hsv_hist(hair_region).tolist()
                profile["color_palette"]["hair_hex"] = self._get_dominant_color_hex(hair_region)

        # 2. Upper Torso signature (Shirt / Jacket)
        if "torso_crop" in segments and segments["torso_crop"] is not None and segments["torso_crop"].size > 0:
            torso_crop = segments["torso_crop"]
            profile["torso_signature"] = self._compute_hsv_hist(torso_crop).tolist()
            profile["color_palette"]["torso_hex"] = self._get_dominant_color_hex(torso_crop)

        # 3. Lower Body / Legs signature
        if "legs_crop" in segments and segments["legs_crop"] is not None and segments["legs_crop"].size > 0:
            legs_crop = segments["legs_crop"]
            profile["legs_signature"] = self._compute_hsv_hist(legs_crop).tolist()
            profile["color_palette"]["legs_hex"] = self._get_dominant_color_hex(legs_crop)

        return profile

    def _compute_hsv_hist(self, crop_bgr: np.ndarray) -> np.ndarray:
        """
        Computes normalized 3D HSV color histogram.
        """
        hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist(
            [hsv], [0, 1, 2], None,
            [self.h_bins, self.s_bins, self.v_bins],
            [0, 180, 0, 256, 0, 256]
        )
        hist = cv2.normalize(hist, hist).flatten()
        return hist.astype(np.float32)

    def _get_dominant_color_hex(self, crop_bgr: np.ndarray) -> str:
        """
        Extracts dominant representative RGB color and formats as HEX string.
        """
        try:
            pixels = crop_bgr.reshape(-1, 3).astype(np.float32)
            if len(pixels) < 10:
                return "#555555"
            # Subsample for speed
            sample = pixels[np.random.choice(len(pixels), min(100, len(pixels)), replace=False)]
            # Mean BGR
            mean_bgr = np.median(sample, axis=0)
            b, g, r = int(mean_bgr[0]), int(mean_bgr[1]), int(mean_bgr[2])
            return f"#{r:02x}{g:02x}{b:02x}".upper()
        except Exception:
            return "#3B82F6"

    def match_appearance(self, current_profile: Dict[str, Any], registered_profile: Dict[str, Any]) -> float:
        """
        Compares current appearance against registered profile using Bhattacharyya distance.
        Returns match score from 0.0 to 1.0.
        """
        scores = []
        weights = []

        # Torso comparison (heaviest weight)
        if current_profile.get("torso_signature") and registered_profile.get("torso_signature"):
            t_curr = np.array(current_profile["torso_signature"], dtype=np.float32)
            t_reg = np.array(registered_profile["torso_signature"], dtype=np.float32)
            # cv2.HISTCMP_BHATTACHARYYA: 0.0 is identical, 1.0 is completely different
            b_dist = cv2.compareHist(t_curr, t_reg, cv2.HISTCMP_BHATTACHARYYA)
            torso_score = max(0.0, 1.0 - b_dist)
            scores.append(torso_score)
            weights.append(0.55)

        # Head / Hair comparison (great for back & overhead)
        if current_profile.get("head_signature") and registered_profile.get("head_signature"):
            h_curr = np.array(current_profile["head_signature"], dtype=np.float32)
            h_reg = np.array(registered_profile["head_signature"], dtype=np.float32)
            b_dist = cv2.compareHist(h_curr, h_reg, cv2.HISTCMP_BHATTACHARYYA)
            head_score = max(0.0, 1.0 - b_dist)
            scores.append(head_score)
            weights.append(0.25)

        # Legs comparison
        if current_profile.get("legs_signature") and registered_profile.get("legs_signature"):
            l_curr = np.array(current_profile["legs_signature"], dtype=np.float32)
            l_reg = np.array(registered_profile["legs_signature"], dtype=np.float32)
            b_dist = cv2.compareHist(l_curr, l_reg, cv2.HISTCMP_BHATTACHARYYA)
            legs_score = max(0.0, 1.0 - b_dist)
            scores.append(legs_score)
            weights.append(0.20)

        if not scores:
            return 0.0

        total_weight = sum(weights)
        combined_score = sum(s * w for s, w in zip(scores, weights)) / total_weight
        return float(combined_score)
