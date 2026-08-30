"""
Face Biometrics and Embedding Extractor for Target Identification.
Generates 128-dimensional biometric embeddings and calculates match confidence.
"""
import cv2
import numpy as np
from typing import Optional, List, Dict, Any, Tuple

# Attempt to import face_recognition
try:
    import face_recognition
    FACE_REC_AVAILABLE = True
except ImportError:
    FACE_REC_AVAILABLE = False


class FaceBiometricsEngine:
    def __init__(self):
        self.available = FACE_REC_AVAILABLE
        # Fallback OpenCV Haar Cascade
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )

    def extract_face_embedding(self, frame_bgr: np.ndarray, head_crop: Optional[np.ndarray] = None) -> Optional[Dict[str, Any]]:
        """
        Extracts face location and 128D biometric vector.
        """
        image_to_scan = head_crop if head_crop is not None and head_crop.size > 0 else frame_bgr
        h, w, c = image_to_scan.shape
        if h < 30 or w < 30:
            return None

        rgb_img = cv2.cvtColor(image_to_scan, cv2.COLOR_BGR2RGB)

        if self.available:
            try:
                # Detect face locations
                face_locations = face_recognition.face_locations(rgb_img, model="hog")
                if not face_locations:
                    # Retry with slight upsample
                    face_locations = face_recognition.face_locations(rgb_img, number_of_times_to_upsample=1)
                
                if not face_locations:
                    return None

                # Extract 128D embeddings
                encodings = face_recognition.face_encodings(rgb_img, face_locations)
                if encodings:
                    top, right, bottom, left = face_locations[0]
                    return {
                        "embedding": encodings[0].tolist(),
                        "face_box": [int(left), int(top), int(right - left), int(bottom - top)],
                        "confidence": 0.95,
                        "type": "dlib_128d"
                    }
            except Exception as e:
                pass

        # Fallback using OpenCV Haar + Color Eigen Features
        gray = cv2.cvtColor(image_to_scan, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
        if len(faces) > 0:
            x, y, fw, fh = faces[0]
            face_roi = gray[y:y+fh, x:x+fw]
            face_resized = cv2.resize(face_roi, (32, 32))
            # Normalized 128D synthetic feature descriptor
            hist = cv2.calcHist([face_resized], [0], None, [128], [0, 256]).flatten()
            norm_hist = hist / (np.linalg.norm(hist) + 1e-6)
            return {
                "embedding": norm_hist.tolist(),
                "face_box": [int(x), int(y), int(fw), int(fh)],
                "confidence": 0.70,
                "type": "haar_hist_128d"
            }

        return None

    def compare_embeddings(self, embedding_a: List[float], embedding_b: List[float]) -> float:
        """
        Calculates similarity score (0.0 to 1.0) between two face embeddings.
        1.0 is exact match.
        """
        if not embedding_a or not embedding_b or len(embedding_a) != len(embedding_b):
            return 0.0

        vec_a = np.array(embedding_a, dtype=np.float32)
        vec_b = np.array(embedding_b, dtype=np.float32)

        # Euclidean distance
        dist = np.linalg.norm(vec_a - vec_b)
        
        # Face_recognition standard: < 0.6 is same person
        # Convert distance to a 0.0 - 1.0 confidence score
        if dist < 0.60:
            score = 1.0 - (dist / 1.2)
        else:
            score = max(0.0, 1.0 - (dist / 0.8))

        return float(np.clip(score, 0.0, 1.0))
