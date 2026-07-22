"""Camera capture module for kyyy.

Supports multiple camera backends with automatic fallback,
and gracefully handles disconnects / unsupported resolutions.
"""

import time
from typing import Optional, Tuple

import cv2
import numpy as np

# Camera backends in order of preference (Windows-only project)
_CAMERA_BACKENDS = [
    ("DirectShow", cv2.CAP_DSHOW),
    ("MSMF",       cv2.CAP_MSMF),
    ("Default",    cv2.CAP_ANY),
]


def _get_backend_name(backend_id: int) -> str:
    for name, bid in _CAMERA_BACKENDS:
        if bid == backend_id:
            return name
    return "Unknown"


class CameraManager:
    """Manages USB/webcam capture via OpenCV VideoCapture.

    Falls back through available backends if the primary fails.
    Handles reconnection and resolution negotiation.
    """

    def __init__(self, camera_id: int = 0, flip_horizontal: bool = True,
                 target_width: int = 640, target_height: int = 480,
                 target_fps: int = 30):
        self._camera_id = camera_id
        self._flip_horizontal = flip_horizontal
        self._target_w = target_width
        self._target_h = target_height
        self._target_fps = target_fps

        self._cap: Optional[cv2.VideoCapture] = None
        self._backend_idx = 0  # which backend we're trying
        self._last_frame: Optional[np.ndarray] = None
        self._connected = False
        self._reconnect_interval = 2.0
        self._last_attempt = 0.0

    # ── Open / reconnect ──────────────────────────────────────────

    def open(self) -> bool:
        """Open the camera, trying each backend until one succeeds."""
        for idx, (name, backend) in enumerate(_CAMERA_BACKENDS):
            try:
                cap = cv2.VideoCapture(self._camera_id, backend)
                if cap.isOpened():
                    self._cap = cap
                    self._backend_idx = idx
                    self._configure_capture()
                    self._connected = True
                    return True
                else:
                    cap.release()
            except Exception as e:
                print(f"[Camera] Backend '{name}' error: {e}")
                continue

        print(f"[Camera] ERROR: No backend could open camera {self._camera_id}")
        self._connected = False
        return False

    def _configure_capture(self) -> None:
        """Apply resolution / FPS settings and log actual values."""
        if self._cap is None:
            return
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._target_w)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._target_h)
        self._cap.set(cv2.CAP_PROP_FPS, self._target_fps)

        actual_w = self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_h = self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        actual_fps = self._cap.get(cv2.CAP_PROP_FPS)
        backend_name = _CAMERA_BACKENDS[self._backend_idx][0]

        if abs(actual_w - self._target_w) > 10 or abs(actual_h - self._target_h) > 10:
            print(f"[Camera] Note: requested {self._target_w}x{self._target_h}, "
                  f"got {actual_w:.0f}x{actual_h:.0f} (backend: {backend_name})")

        print(f"[Camera] Opened camera {self._camera_id}: "
              f"{actual_w:.0f}x{actual_h:.0f} @ {actual_fps:.0f}fps [{backend_name}]")

    # ── Frame reading ─────────────────────────────────────────────

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read a frame. Returns (success, BGR frame or None)."""
        if not self._connected:
            return self._try_reconnect()

        try:
            if self._cap is None:
                self._connected = False
                return False, None

            success, frame = self._cap.read()
            if not success or frame is None or frame.size == 0:
                print("[Camera] Frame read failed — marking disconnected.")
                self._connected = False
                return False, None

            if self._flip_horizontal:
                frame = cv2.flip(frame, 1)

            self._last_frame = frame
            return True, frame

        except Exception as e:
            print(f"[Camera] Error reading frame: {e}")
            self._connected = False
            return False, None

    def _try_reconnect(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Attempt periodic reconnection."""
        now = time.time()
        if now - self._last_attempt > self._reconnect_interval:
            self._last_attempt = now
            print("[Camera] Attempting to reconnect...")
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None
            self.open()
        return False, None

    # ── Accessors ─────────────────────────────────────────────────

    def get_frame_size(self) -> Tuple[int, int]:
        """Get last frame dimensions (width, height), or fallback default."""
        if self._last_frame is not None:
            h, w = self._last_frame.shape[:2]
            return w, h
        return self._target_w, self._target_h

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def connected(self) -> bool:
        """Alias for is_connected (used by app.py)."""
        return self._connected

    def release(self) -> None:
        """Release camera resources."""
        self._connected = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        print("[Camera] Released.")
