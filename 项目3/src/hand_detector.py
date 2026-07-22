"""Hand and fingertip detection using MediaPipe Hands.

Supports both the legacy mp.solutions API (mediapipe < 0.10.10)
and the newer mp.tasks API (mediapipe >= 0.10.10) with automatic
model download on first run.
"""

import os
import urllib.request
from typing import List, Optional, Tuple

import cv2
import numpy as np

# ── Constants (same in both APIs) ────────────────────────────────

INDEX_FINGER_TIP = 8
THUMB_TIP = 4

# Hand landmark connections: (start_idx, end_idx)
HAND_CONNECTIONS: List[Tuple[int, int]] = [
    (3, 4), (0, 5), (17, 18), (0, 17), (13, 14), (13, 17), (18, 19),
    (5, 6), (5, 9), (14, 15), (0, 1), (9, 10), (1, 2), (9, 13),
    (10, 11), (19, 20), (6, 7), (15, 16), (2, 3), (11, 12), (7, 8),
]

# Model file for new tasks API
_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
)
_MODEL_FILENAME = "hand_landmarker.task"


# ── API detection ────────────────────────────────────────────────

def _detect_api():
    """Return ('legacy', module) or ('tasks', module) based on installed version."""
    import mediapipe as mp
    if hasattr(mp, 'solutions') and hasattr(mp.solutions, 'hands'):
        return 'legacy', mp
    return 'tasks', mp


_API_MODE, _MP = _detect_api()


# ── Drawing utilities (lazy-loaded per API) ──────────────────────

def _get_drawing_utils():
    """Return (drawing_utils, drawing_styles) for the active API."""
    if _API_MODE == 'legacy':
        return _MP.solutions.drawing_utils, _MP.solutions.drawing_styles
    else:
        from mediapipe.tasks.python.vision import (
            drawing_utils,
            drawing_styles,
        )
        return drawing_utils, drawing_styles


# ── Model download ───────────────────────────────────────────────

def _ensure_model() -> str:
    """Ensure the hand landmarker model file exists locally.

    Stores the model in a path safe for the MediaPipe C++ backend
    (avoids non-ASCII characters like Chinese in the path).

    Returns the path to the model file, downloading it if necessary.
    """
    # Use LOCALAPPDATA for an ASCII-safe cache directory
    local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    cache_dir = os.path.join(local_appdata, "ARKeyboard", "models")
    os.makedirs(cache_dir, exist_ok=True)
    model_path = os.path.join(cache_dir, _MODEL_FILENAME)

    if not os.path.exists(model_path):
        print(f"[HandDetector] Downloading hand landmarker model...")
        print(f"[HandDetector]   from: {_MODEL_URL}")
        try:
            urllib.request.urlretrieve(_MODEL_URL, model_path)
            size_mb = os.path.getsize(model_path) / (1024 * 1024)
            print(f"[HandDetector]   saved: {model_path} ({size_mb:.1f} MB)")
        except Exception as e:
            print(f"[HandDetector] ERROR downloading model: {e}")
            print("[HandDetector] Please download manually from:")
            print(f"  {_MODEL_URL}")
            print(f"  and save to: {model_path}")
            raise
    return model_path


# ── HandDetector class ───────────────────────────────────────────

class HandDetector:
    """Detects hand landmarks and extracts smoothed index-fingertip position.

    Works with both legacy mediapipe.solutions (0.10.0–0.10.9) and
    newer mediapipe.tasks (0.10.10+) APIs.
    """

    def __init__(
        self,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.5,
        smoothing_alpha: float = 0.40,
        max_num_hands: int = 1,
    ):
        self._smoothing_alpha = smoothing_alpha

        # EMA smoothing state
        self._smoothed_x: Optional[float] = None
        self._smoothed_y: Optional[float] = None
        self._hand_present = False

        # Latest results (format depends on API mode)
        self._latest_results = None  # legacy: mp SolutionResult
        self._latest_tasks_result = None  # tasks: HandLandmarkerResult

        print(f"[HandDetector] Initializing MediaPipe Hands (API: {_API_MODE})...")

        if _API_MODE == 'legacy':
            self._init_legacy(min_detection_confidence, min_tracking_confidence, max_num_hands)
        else:
            self._init_tasks(min_detection_confidence, min_tracking_confidence, max_num_hands)

        print("[HandDetector] MediaPipe Hands ready.")

    # ── Legacy API init (mediapipe 0.10.0 – 0.10.9) ─────────────

    def _init_legacy(self, min_det_conf: float, min_track_conf: float, max_hands: int):
        self._mp_hands_mod = _MP.solutions.hands
        self._hands = self._mp_hands_mod.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=min_det_conf,
            min_tracking_confidence=min_track_conf,
        )

    # ── New Tasks API init (mediapipe 0.10.10+) ──────────────────

    def _init_tasks(self, min_det_conf: float, min_track_conf: float, max_hands: int):
        from mediapipe.tasks.python.vision import (
            HandLandmarker,
            HandLandmarkerOptions,
        )
        from mediapipe.tasks.python.core.base_options import BaseOptions
        from mediapipe.tasks.python.vision.core.vision_task_running_mode import (
            VisionTaskRunningMode,
        )

        model_path = _ensure_model()

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionTaskRunningMode.IMAGE,
            num_hands=max_hands,
            min_hand_detection_confidence=min_det_conf,
            min_tracking_confidence=min_track_conf,
        )
        self._hand_landmarker = HandLandmarker.create_from_options(options)

    # ── Detection ────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> Optional[Tuple[int, int]]:
        """Detect index fingertip in a BGR frame.

        Returns (pixel_x, pixel_y) of the smoothed index fingertip,
        or None if no hand is detected.
        """
        if _API_MODE == 'legacy':
            return self._detect_legacy(frame)
        else:
            return self._detect_tasks(frame)

    def _detect_legacy(self, frame: np.ndarray) -> Optional[Tuple[int, int]]:
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self._hands.process(rgb)
        rgb.flags.writeable = True
        self._latest_results = results

        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks[0]
            tip = hand_landmarks.landmark[INDEX_FINGER_TIP]
            return self._apply_smoothing(tip.x * w, tip.y * h)
        else:
            self._hand_present = False
            self._smoothed_x = None
            self._smoothed_y = None
            return None

    def _detect_tasks(self, frame: np.ndarray) -> Optional[Tuple[int, int]]:
        import mediapipe as mp  # for mp.Image

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._hand_landmarker.detect(mp_image)
        self._latest_tasks_result = result

        if result.hand_landmarks and len(result.hand_landmarks) > 0:
            hand = result.hand_landmarks[0]
            tip = hand[INDEX_FINGER_TIP]
            return self._apply_smoothing(tip.x * w, tip.y * h)
        else:
            self._hand_present = False
            self._smoothed_x = None
            self._smoothed_y = None
            return None

    # ── EMA smoothing ────────────────────────────────────────────

    def _apply_smoothing(self, raw_x: float, raw_y: float) -> Tuple[int, int]:
        if self._smoothed_x is None or not self._hand_present:
            self._smoothed_x = raw_x
            self._smoothed_y = raw_y
        else:
            a = self._smoothing_alpha
            self._smoothed_x = a * raw_x + (1 - a) * self._smoothed_x
            self._smoothed_y = a * raw_y + (1 - a) * self._smoothed_y

        self._hand_present = True
        return (int(self._smoothed_x), int(self._smoothed_y))

    # ── Extra accessors ──────────────────────────────────────────

    def get_index_tip_raw(self) -> Optional[Tuple[float, float]]:
        """Get the raw (unsmoothed) index fingertip in normalized coords [0,1]."""
        if _API_MODE == 'legacy':
            if self._latest_results is None or not self._latest_results.multi_hand_landmarks:
                return None
            hand = self._latest_results.multi_hand_landmarks[0]
            tip = hand.landmark[INDEX_FINGER_TIP]
            return (tip.x, tip.y)
        else:
            if self._latest_tasks_result is None or not self._latest_tasks_result.hand_landmarks:
                return None
            hand = self._latest_tasks_result.hand_landmarks[0]
            tip = hand[INDEX_FINGER_TIP]
            return (tip.x, tip.y)

    def get_pinch_distance(self) -> Optional[float]:
        """Return Euclidean distance between thumb tip (4) and index tip (8),
        in normalized coordinates [0, 1]. None if no hand detected.
        """
        if _API_MODE == 'legacy':
            if self._latest_results is None or not self._latest_results.multi_hand_landmarks:
                return None
            hand = self._latest_results.multi_hand_landmarks[0]
            thumb = hand.landmark[THUMB_TIP]
            index = hand.landmark[INDEX_FINGER_TIP]
        else:
            if self._latest_tasks_result is None or not self._latest_tasks_result.hand_landmarks:
                return None
            hand = self._latest_tasks_result.hand_landmarks[0]
            thumb = hand[THUMB_TIP]
            index = hand[INDEX_FINGER_TIP]

        dx = thumb.x - index.x
        dy = thumb.y - index.y
        return (dx * dx + dy * dy) ** 0.5

    def _get_all_landmarks(self):
        """Return the full list of 21 landmarks for the first detected hand.

        Returns a list of landmark objects (each with .x, .y in [0,1]),
        or None if no hand is detected.  Works with both API modes.
        """
        if _API_MODE == 'legacy':
            if self._latest_results is None or not self._latest_results.multi_hand_landmarks:
                return None
            return list(self._latest_results.multi_hand_landmarks[0].landmark)
        else:
            if self._latest_tasks_result is None or not self._latest_tasks_result.hand_landmarks:
                return None
            return list(self._latest_tasks_result.hand_landmarks[0])

    # ── Drawing ──────────────────────────────────────────────────

    def draw_landmarks(self, frame: np.ndarray) -> None:
        """Draw hand landmarks on the frame for debug visualization."""
        if _API_MODE == 'legacy':
            self._draw_landmarks_legacy(frame)
        else:
            self._draw_landmarks_tasks(frame)

    def _draw_landmarks_legacy(self, frame: np.ndarray) -> None:
        drawing_utils, drawing_styles = _get_drawing_utils()
        if self._latest_results and self._latest_results.multi_hand_landmarks:
            for hand_landmarks in self._latest_results.multi_hand_landmarks:
                drawing_utils.draw_landmarks(
                    frame,
                    hand_landmarks,
                    self._mp_hands_mod.HAND_CONNECTIONS,
                    drawing_styles.get_default_hand_landmarks_style(),
                    drawing_styles.get_default_hand_connections_style(),
                )

    def _draw_landmarks_tasks(self, frame: np.ndarray) -> None:
        drawing_utils, drawing_styles = _get_drawing_utils()
        result = self._latest_tasks_result
        if result is None or not result.hand_landmarks:
            return

        # New API drawing: per-hand landmark list + connection list
        for hand in result.hand_landmarks:
            drawing_utils.draw_landmarks(
                frame,
                hand,
                HAND_CONNECTIONS,
                landmark_drawing_spec=drawing_utils.DrawingSpec(
                    color=(0, 255, 0), thickness=2, circle_radius=2
                ),
                connection_drawing_spec=drawing_utils.DrawingSpec(
                    color=(224, 224, 224), thickness=2, circle_radius=2
                ),
            )

    # ── Cleanup ──────────────────────────────────────────────────

    @property
    def is_hand_present(self) -> bool:
        return self._hand_present

    def release(self) -> None:
        """Release MediaPipe resources."""
        if _API_MODE == 'legacy':
            self._hands.close()
        else:
            self._hand_landmarker.close()
        print("[HandDetector] Released.")
