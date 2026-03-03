"""
SENTINEL — Face Recognition Module
Uses MediaPipe FaceLandmarker (Tasks API 0.10.x) for face detection,
encoding extraction, and cosine-similarity-based face verification.
"""

import cv2
import mediapipe as mp
import numpy as np
import os

from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)
from mediapipe.tasks.python import BaseOptions

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "face_landmarker.task")


class FaceRecognizer:
    """
    Face recognition using MediaPipe FaceLandmarker.

    Registration:  capture multiple face images → extract landmark encodings → average → store
    Verification:  capture one image → extract encoding → cosine similarity against stored encodings
    """

    def __init__(self):
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"Face landmarker model not found at {MODEL_PATH}\n"
                "Run the app once — it will auto-download the model."
            )

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
        )
        self.landmarker = FaceLandmarker.create_from_options(options)

    # ──────────────────────────────────────────
    # Encoding
    # ──────────────────────────────────────────
    def extract_encoding(self, image_rgb: np.ndarray):
        """
        Extract a normalized face encoding from an RGB image.

        Returns a 1-D numpy array (478 landmarks × 3 coords = 1434 values),
        or None if no face is detected.
        """
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb.copy())
        result = self.landmarker.detect(mp_image)

        if not result.face_landmarks or len(result.face_landmarks) == 0:
            return None

        landmarks = result.face_landmarks[0]
        # 478 landmarks, each with (x, y, z) normalised coords
        coords = np.array([[lm.x, lm.y, lm.z] for lm in landmarks], dtype=np.float64)

        # Centre around centroid for position invariance
        centroid = coords.mean(axis=0)
        coords = coords - centroid

        # Scale to unit norm for size invariance
        norm = np.linalg.norm(coords)
        if norm > 0:
            coords = coords / norm

        return coords.flatten()

    def detect_face_box(self, image_rgb: np.ndarray):
        """
        Detect a face and return bounding box info for UI drawing.
        Returns (found, bbox_dict) where bbox_dict has x, y, w, h in pixel coords.
        """
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb.copy())
        result = self.landmarker.detect(mp_image)

        if not result.face_landmarks or len(result.face_landmarks) == 0:
            return False, None

        landmarks = result.face_landmarks[0]
        h, w = image_rgb.shape[:2]

        xs = [lm.x * w for lm in landmarks]
        ys = [lm.y * h for lm in landmarks]

        x_min, x_max = int(min(xs)), int(max(xs))
        y_min, y_max = int(min(ys)), int(max(ys))

        # Add padding
        pad = 20
        x_min = max(0, x_min - pad)
        y_min = max(0, y_min - pad)
        x_max = min(w, x_max + pad)
        y_max = min(h, y_max + pad)

        return True, {
            "x": x_min, "y": y_min,
            "w": x_max - x_min, "h": y_max - y_min,
        }

    # ──────────────────────────────────────────
    # Similarity
    # ──────────────────────────────────────────
    @staticmethod
    def cosine_similarity(enc1: np.ndarray, enc2: np.ndarray) -> float:
        """Cosine similarity in [-1, 1] (higher = more similar)."""
        dot = np.dot(enc1, enc2)
        n1 = np.linalg.norm(enc1)
        n2 = np.linalg.norm(enc2)
        if n1 == 0 or n2 == 0:
            return 0.0
        return float(dot / (n1 * n2))

    # ──────────────────────────────────────────
    # Registration
    # ──────────────────────────────────────────
    def register_face(self, frames: list, min_samples: int = 3):
        """
        Build a face encoding from multiple RGB frames.

        Args:
            frames:      list of RGB numpy images
            min_samples: minimum successful detections required

        Returns:
            (encoding, message)  where encoding is None on failure
        """
        encodings = []
        for frame in frames:
            enc = self.extract_encoding(frame)
            if enc is not None:
                encodings.append(enc)

        if len(encodings) < min_samples:
            return None, (
                f"Only {len(encodings)}/{len(frames)} faces detected. "
                f"Need at least {min_samples}. Please try again with better lighting."
            )

        avg = np.mean(encodings, axis=0)
        # Re-normalise
        norm = np.linalg.norm(avg)
        if norm > 0:
            avg = avg / norm

        return avg, f"Face registered with {len(encodings)} samples ✅"

    # ──────────────────────────────────────────
    # Verification
    # ──────────────────────────────────────────
    def verify_face(self, image_rgb: np.ndarray, stored_encodings: list,
                    threshold: float = 0.80):
        """
        Verify a face against stored user encodings.

        Args:
            image_rgb:         RGB image to test
            stored_encodings:  list of dicts {user_id, username, encoding}
            threshold:         minimum similarity score to accept

        Returns:
            (matched: bool, user_info: dict|None, score: float)
        """
        current = self.extract_encoding(image_rgb)
        if current is None:
            return False, None, 0.0

        best_match = None
        best_score = -1.0

        for user_data in stored_encodings:
            score = self.cosine_similarity(current, user_data["encoding"])
            if score > best_score:
                best_score = score
                best_match = user_data

        if best_match and best_score >= threshold:
            return True, best_match, best_score

        return False, best_match, best_score

    # ──────────────────────────────────────────
    def close(self):
        self.landmarker.close()


# ──────────────────────────────────────────────
# Model downloader (called from app.py on startup)
# ──────────────────────────────────────────────
def ensure_face_model():
    """Download the face landmarker model if it doesn't exist."""
    if os.path.exists(MODEL_PATH):
        return True

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

    url = (
        "https://storage.googleapis.com/mediapipe-models/"
        "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
    )
    print(f"Downloading face landmarker model to {MODEL_PATH} ...")

    try:
        import urllib.request
        urllib.request.urlretrieve(url, MODEL_PATH)
        print("Face model downloaded ✅")
        return True
    except Exception as e:
        print(f"Failed to download face model: {e}")
        return False


def ensure_hand_model():
    """Download the hand landmarker model if it doesn't exist."""
    hand_path = os.path.join(PROJECT_ROOT, "models", "hand_landmarker.task")
    if os.path.exists(hand_path):
        return True

    os.makedirs(os.path.dirname(hand_path), exist_ok=True)

    url = (
        "https://storage.googleapis.com/mediapipe-models/"
        "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
    )
    print(f"Downloading hand landmarker model to {hand_path} ...")

    try:
        import urllib.request
        urllib.request.urlretrieve(url, hand_path)
        print("Hand model downloaded ✅")
        return True
    except Exception as e:
        print(f"Failed to download hand model: {e}")
        return False
