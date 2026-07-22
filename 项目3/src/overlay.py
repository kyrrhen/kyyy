"""Keyboard layout overlay renderer for kyyy.

Draws a 3×4 9-key grid as a semi-transparent overlay on the camera frame.
Supports left-side and bottom placement, with 3D lift effect on hover.

Layout (phone-style T9 arrangement):

    [1]  [2]  [3]
    [4]  [5]  [6]
    [7]  [8]  [9]
    [BS] [SP] [ENTER]
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

NUM_KEYS = 12
NUM_COLS = 3
NUM_ROWS = 4

# Imported from keyboard_sender as single source of truth
from .keyboard_sender import KEY_LABELS  # noqa: E402

_MIN_FRAME_W = 60
_MIN_FRAME_H = 80

# How far the hovered key "lifts" (pixel offset up+left)
_LIFT_OFFSET = 4
# Shadow size beneath a lifted key
_SHADOW_OFFSET = 4
_SHADOW_COLOR = (0, 0, 0)


@dataclass
class KeyRect:
    """Bounding box of a single key in pixel coordinates."""
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def contains(self, px: int, py: int) -> bool:
        return self.left <= px <= self.right and self.top <= py <= self.bottom


class OverlayRenderer:
    """Renders the 9-key keyboard overlay with alpha blending.

    Supports:
      - Left-side or bottom keyboard positioning
      - 3D "lift" effect on hovered key
      - Auto-scaling fonts and margins
    """

    def __init__(
        self,
        keyboard_alpha: float = 0.25,
        keyboard_position: str = "left",
        keyboard_size_ratio: float = 0.35,
        margin_px: int = 6,
        key_normal_color: Tuple[int, int, int] = (200, 200, 200),
        key_hover_color: Tuple[int, int, int] = (255, 200, 60),
        key_highlight_color: Tuple[int, int, int] = (0, 255, 0),
        key_border_color: Tuple[int, int, int] = (140, 140, 140),
        key_text_color: Tuple[int, int, int] = (255, 255, 255),
        keyboard_bg_color: Tuple[int, int, int] = (20, 20, 20),
        font_scale: float = 1.0,
        border_thickness: int = 2,
        label_thickness: int = 2,
    ):
        self.keyboard_alpha = keyboard_alpha
        self.position = keyboard_position          # "left" or "bottom"
        self.size_ratio = keyboard_size_ratio       # fraction of width or height
        self.margin_px = margin_px
        self.key_normal_color = key_normal_color
        self.key_hover_color = key_hover_color
        self.key_highlight_color = key_highlight_color
        self.key_border_color = key_border_color
        self.key_text_color = key_text_color
        self.keyboard_bg_color = keyboard_bg_color
        self.font_scale = font_scale
        self.border_thickness = border_thickness
        self.label_thickness = label_thickness

    # Backward-compat alias so app.py still works
    @property
    def keyboard_height_ratio(self) -> float:
        return self.size_ratio

    @keyboard_height_ratio.setter
    def keyboard_height_ratio(self, val: float) -> None:
        self.size_ratio = val

    # ── Layout computation ────────────────────────────────────────

    def compute_key_rects(self, frame_width: int,
                          frame_height: int) -> List[KeyRect]:
        """Compute 12 key bounding rectangles for the 3×4 grid.

        When position='left', the keyboard occupies the left
        `size_ratio` of the frame width, stacked vertically.
        When position='bottom', it occupies the bottom portion (legacy).
        """
        cols, rows = NUM_COLS, NUM_ROWS

        if self.position == "left":
            # ── Left-side layout ──────────────────────────────────
            kb_width = max(1, int(frame_width * self.size_ratio))
            kb_height = frame_height

            col_w = max(1, kb_width // cols)
            row_h = max(1, kb_height // rows)

            max_margin = max(0, min(col_w // 3, row_h // 3, self.margin_px))

            rects = []
            for row in range(rows):
                for col in range(cols):
                    x = max(0, col * col_w + max_margin)
                    y = max(0, row * row_h + max_margin)
                    w = max(1, col_w - 2 * max_margin)
                    h = max(1, row_h - 2 * max_margin)
                    rects.append(KeyRect(x, y, w, h))
            return rects

        else:
            # ── Bottom layout (legacy) ────────────────────────────
            kb_top = int(frame_height * (1.0 - self.size_ratio))
            kb_height = max(1, frame_height - kb_top)

            col_w = max(1, frame_width // cols)
            row_h = max(1, kb_height // rows)

            max_margin = max(0, min(col_w // 3, row_h // 3, self.margin_px))

            rects = []
            for row in range(rows):
                for col in range(cols):
                    x = max(0, col * col_w + max_margin)
                    y = max(0, kb_top + row * row_h + max_margin)
                    w = max(1, col_w - 2 * max_margin)
                    h = max(1, row_h - 2 * max_margin)
                    rects.append(KeyRect(x, y, w, h))
            return rects

    # ── Rendering ─────────────────────────────────────────────────

    def render(
        self,
        frame: np.ndarray,
        key_rects: List[KeyRect],
        hovered_key: int = -1,
        triggered_key: int = -1,
        show_key_boundaries: bool = False,
    ) -> np.ndarray:
        """Draw the keyboard overlay on a copy of the frame."""
        h, w = frame.shape[:2]

        if w < _MIN_FRAME_W or h < _MIN_FRAME_H:
            return frame.copy()

        overlay = frame.copy()

        # ── 1. Keyboard background ────────────────────────────────
        self._draw_background(overlay, frame, h, w)

        # ── 2. Individual keys ────────────────────────────────────
        self._draw_keys(overlay, frame, key_rects, hovered_key,
                        triggered_key, show_key_boundaries, h, w)

        # ── 3. Overall blend ──────────────────────────────────────
        result = cv2.addWeighted(frame, 0.55, overlay, 0.45, 0)

        # ── 4. Labels ─────────────────────────────────────────────
        self._draw_labels(result, key_rects, hovered_key)

        return result

    # ── Sub-steps ─────────────────────────────────────────────────

    def _get_keyboard_roi(self, h: int, w: int) -> Tuple[int, int, int, int]:
        """Return (x1, y1, x2, y2) of the keyboard background area."""
        if self.position == "left":
            kb_w = int(w * self.size_ratio)
            return (0, 0, kb_w, h)
        else:
            kb_top = int(h * (1.0 - self.size_ratio))
            return (0, kb_top, w, h)

    def _draw_background(self, overlay: np.ndarray, frame: np.ndarray,
                         h: int, w: int) -> None:
        """Darken the keyboard area."""
        x1, y1, x2, y2 = self._get_keyboard_roi(h, w)
        bg_roi = overlay[y1:y2, x1:x2]
        if bg_roi.size > 0:
            bg_overlay = np.full_like(bg_roi, self.keyboard_bg_color, dtype=np.uint8)
            blended = cv2.addWeighted(bg_roi, 1.0 - self.keyboard_alpha,
                                      bg_overlay, self.keyboard_alpha, 0)
            overlay[y1:y2, x1:x2] = blended

    def _draw_keys(self, overlay: np.ndarray, frame: np.ndarray,
                   key_rects: List[KeyRect], hovered_key: int,
                   triggered_key: int, show_boundaries: bool,
                   h: int, w: int) -> None:
        """Draw each key with appropriate fill, border, and lift effect."""
        for i, rect in enumerate(key_rects):
            x1 = max(0, rect.left)
            y1 = max(0, rect.top)
            x2 = min(w, rect.right)
            y2 = min(h, rect.bottom)
            if x2 <= x1 or y2 <= y1:
                continue

            is_hovered = (i == hovered_key)
            is_triggered = (i == triggered_key)
            is_active = is_hovered or is_triggered

            # ── Lift effect (shadow + offset) ─────────────────
            if is_hovered and not is_triggered:
                lift_x1 = max(0, x1 - _LIFT_OFFSET)
                lift_y1 = max(0, y1 - _LIFT_OFFSET)
                lift_x2 = min(w, x2 - _LIFT_OFFSET)
                lift_y2 = min(h, y2 - _LIFT_OFFSET)

                # Shadow
                shadow_x1 = x1 + _SHADOW_OFFSET
                shadow_y1 = y1 + _SHADOW_OFFSET
                shadow_x2 = min(w, x2 + _SHADOW_OFFSET)
                shadow_y2 = min(h, y2 + _SHADOW_OFFSET)

                if shadow_x2 > shadow_x1 and shadow_y2 > shadow_y1:
                    cv2.rectangle(overlay, (shadow_x1, shadow_y1),
                                  (shadow_x2, shadow_y2),
                                  _SHADOW_COLOR, -1)
                    shadow_roi_f = frame[shadow_y1:shadow_y2, shadow_x1:shadow_x2]
                    shadow_roi_o = overlay[shadow_y1:shadow_y2, shadow_x1:shadow_x2]
                    if shadow_roi_f.size > 0:
                        blended_s = cv2.addWeighted(shadow_roi_f, 0.7,
                                                    shadow_roi_o, 0.3, 0)
                        overlay[shadow_y1:shadow_y2, shadow_x1:shadow_x2] = blended_s

                draw_x1, draw_y1 = lift_x1, lift_y1
                draw_x2, draw_y2 = lift_x2, lift_y2
            else:
                draw_x1, draw_y1, draw_x2, draw_y2 = x1, y1, x2, y2

            # ── Fill color ───────────────────────────────────
            if is_triggered:
                fill = self.key_highlight_color
                fill_a = 0.70
            elif is_hovered:
                fill = self.key_hover_color
                fill_a = 0.50
            else:
                fill = self.key_normal_color
                fill_a = 0.18

            # ── Draw fill ────────────────────────────────────
            if draw_x2 > draw_x1 and draw_y2 > draw_y1:
                cv2.rectangle(overlay, (draw_x1, draw_y1),
                              (draw_x2, draw_y2), fill, -1)
                roi_f = frame[draw_y1:draw_y2, draw_x1:draw_x2]
                roi_o = overlay[draw_y1:draw_y2, draw_x1:draw_x2]
                if roi_f.size > 0:
                    blended = cv2.addWeighted(roi_f, 1.0 - fill_a,
                                              roi_o, fill_a, 0)
                    overlay[draw_y1:draw_y2, draw_x1:draw_x2] = blended

            # ── Border ───────────────────────────────────────
            border_t = max(1, self.border_thickness)
            if is_hovered and not is_triggered:
                # 3D raised border: bright top-left, dark bottom-right
                light = tuple(min(255, c + 100) for c in fill)
                dark  = tuple(max(0, c - 80) for c in fill)

                # Top edge (bright) + left edge (bright)
                cv2.line(overlay, (draw_x1, draw_y1), (draw_x2, draw_y1),
                         light, border_t + 2, cv2.LINE_AA)
                cv2.line(overlay, (draw_x1, draw_y1), (draw_x1, draw_y2),
                         light, border_t + 2, cv2.LINE_AA)
                # Bottom edge (dark) + right edge (dark)
                cv2.line(overlay, (draw_x1, draw_y2 - 1),
                         (draw_x2, draw_y2 - 1), dark, border_t + 2, cv2.LINE_AA)
                cv2.line(overlay, (draw_x2 - 1, draw_y1),
                         (draw_x2 - 1, draw_y2), dark, border_t + 2, cv2.LINE_AA)
            else:
                cv2.rectangle(overlay, (draw_x1, draw_y1),
                              (draw_x2, draw_y2),
                              self.key_border_color, border_t)

            if show_boundaries:
                cv2.rectangle(overlay,
                              (draw_x1 - 1, draw_y1 - 1),
                              (draw_x2 + 1, draw_y2 + 1),
                              (0, 0, 255), 1)

    def _draw_labels(self, frame: np.ndarray, key_rects: List[KeyRect],
                     hovered_key: int) -> None:
        """Draw key labels centered in each key."""
        if len(key_rects) == 0:
            return
        avg_h = sum(r.h for r in key_rects) / len(key_rects)
        font_scale = max(0.35, min(3.0, avg_h / 55.0))

        for i, rect in enumerate(key_rects):
            label = KEY_LABELS[i]

            try:
                (tw, th), _ = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, self.label_thickness
                )
            except cv2.error:
                continue

            cx, cy = rect.center
            tx = max(0, cx - tw // 2)
            ty = max(0, cy + th // 2)

            # Hovered key label shifts with the lift
            if i == hovered_key:
                tx = max(0, tx - _LIFT_OFFSET)
                ty = max(0, ty - _LIFT_OFFSET)

            cv2.putText(frame, label, (tx, ty),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                        self.key_text_color, self.label_thickness,
                        cv2.LINE_AA)

    # ── Debug ─────────────────────────────────────────────────────

    def draw_fingertip(
        self,
        frame: np.ndarray,
        fingertip_xy: Optional[Tuple[int, int]],
        color: Tuple[int, int, int] = (0, 0, 255),
        radius: int = 10,
    ) -> None:
        """Draw a circle at the detected fingertip position."""
        if fingertip_xy is not None:
            px, py = fingertip_xy
            cv2.circle(frame, (px, py), radius, color, -1)
            cv2.circle(frame, (px, py), radius + 2, (255, 255, 255), 2, cv2.LINE_AA)
