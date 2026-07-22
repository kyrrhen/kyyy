"""Camera-to-screen coordinate mapping with smoothing.

Maps a normalized hand position in the camera frame to an absolute
screen cursor position.  The preview window can be any size — mapping
always uses the camera's native resolution, normalized to [0,1], then
scaled to the full desktop.

Includes:
  - EMA smoothing to suppress hand tremor
  - Dead zone to ignore micro-movements
  - Adjustable gain/sensitivity
  - Edge margin (keep cursor off exact screen edges)
"""

import ctypes
from typing import Optional, Tuple


class CoordMapper:
    """Maps camera-frame hand position → absolute desktop cursor position."""

    def __init__(
        self,
        smoothing_alpha: float = 0.30,
        dead_zone: float = 0.002,     # fraction of screen — below this, no move
        gain_x: float = 1.8,
        gain_y: float = 1.8,
        edge_margin: int = 4,          # px from screen edge
    ):
        self.smoothing_alpha = smoothing_alpha
        self.dead_zone = dead_zone
        self.gain_x = gain_x
        self.gain_y = gain_y
        self.edge_margin = edge_margin

        # Screen dimensions (cached)
        self._screen_w: int = 1920
        self._screen_h: int = 1080
        self._fetch_screen_size()

        # Smoothed cursor position [0, 1] norm-space
        self._smooth_x: Optional[float] = None
        self._smooth_y: Optional[float] = None

    def _fetch_screen_size(self) -> None:
        """Get primary monitor dimensions via Win32 API."""
        user32 = ctypes.windll.user32
        self._screen_w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        self._screen_h = user32.GetSystemMetrics(1)  # SM_CYSCREEN

    # ── Mapping ───────────────────────────────────────────────────

    def map_to_screen(
        self,
        hand_norm_x: float,
        hand_norm_y: float,
    ) -> Optional[Tuple[int, int]]:
        """Convert a normalized hand position to screen pixel coordinates.

        Args:
            hand_norm_x: [0, 1] — 0 = left edge of camera, 1 = right
            hand_norm_y: [0, 1] — 0 = top edge of camera,  1 = bottom

        Returns:
            (screen_x, screen_y) pixel coords.  Returns None if the
            movement is below the dead zone (cursor stays put).
        """
        # Clamp to [0, 1]
        nx = max(0.0, min(1.0, hand_norm_x))
        ny = max(0.0, min(1.0, hand_norm_y))

        # Apply gain (centered at 0.5)
        cx = 0.5 + (nx - 0.5) * self.gain_x
        cy = 0.5 + (ny - 0.5) * self.gain_y
        cx = max(0.0, min(1.0, cx))
        cy = max(0.0, min(1.0, cy))

        # ── Dead zone: don't update for micro-movements ──────────
        if self._smooth_x is not None and self._smooth_y is not None:
            dx = abs(cx - self._smooth_x)
            dy = abs(cy - self._smooth_y)
            if dx < self.dead_zone and dy < self.dead_zone:
                # Movement too small — return last known screen position
                m = self.edge_margin
                sx = int(m + self._smooth_x * (self._screen_w - 2 * m))
                sy = int(m + self._smooth_y * (self._screen_h - 2 * m))
                return (sx, sy)

        # ── EMA smoothing ─────────────────────────────────────────
        if self._smooth_x is None:
            self._smooth_x = cx
            self._smooth_y = cy
        else:
            a = self.smoothing_alpha
            self._smooth_x = a * cx + (1 - a) * self._smooth_x
            self._smooth_y = a * cy + (1 - a) * self._smooth_y

        # Map [0,1] → screen pixels with edge margin
        m = self.edge_margin
        screen_x = int(m + self._smooth_x * (self._screen_w - 2 * m))
        screen_y = int(m + self._smooth_y * (self._screen_h - 2 * m))

        return (screen_x, screen_y)

    def get_smoothed_norm(self) -> Optional[Tuple[float, float]]:
        """Return current smoothed position in [0, 1]."""
        if self._smooth_x is None:
            return None
        return (self._smooth_x, self._smooth_y)

    def reset(self) -> None:
        """Reset smoothing state."""
        self._smooth_x = None
        self._smooth_y = None

    @property
    def screen_size(self) -> Tuple[int, int]:
        self._fetch_screen_size()
        return (self._screen_w, self._screen_h)
