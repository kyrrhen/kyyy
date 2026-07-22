"""Hand gesture recognition for mouse control.

Detects:
  - Orchid-finger pose (右手兰花指) — the safety-gate baseline pose
  - Index-thumb pinch → left click
  - Middle-thumb pinch → right click
  - Middle-finger vertical slide relative to thumb → scroll wheel

All distance thresholds are in *normalized* [0,1] coordinate space.

Design note:
  Orchid pose (兰花指): thumb tip touches the SIDE of the middle finger
  (around the PIP joint, landmark 10), NOT the middle fingertip.
  This keeps the middle fingertip free so right-click (middle tip → thumb tip)
  is a distinct, physically-separable gesture from the baseline orchid pose.
"""

from typing import List, Optional, Tuple

# MediaPipe hand landmark indices
WRIST           = 0
THUMB_CMC       = 1
THUMB_MCP       = 2
THUMB_IP        = 3
THUMB_TIP       = 4
INDEX_MCP       = 5
INDEX_PIP       = 6
INDEX_DIP       = 7
INDEX_TIP       = 8
MIDDLE_MCP      = 9
MIDDLE_PIP      = 10
MIDDLE_DIP      = 11
MIDDLE_TIP      = 12
RING_MCP        = 13
RING_PIP        = 14
RING_DIP        = 15
RING_TIP        = 16
PINKY_MCP       = 17
PINKY_PIP       = 18
PINKY_DIP       = 19
PINKY_TIP       = 20

# Landmark type: has .x, .y (normalized)
Landmark = object  # duck-typing, works with both legacy and tasks API


class GestureDetector:
    """Gesture recognition for visual mouse control.

    All detection methods operate on a single hand's 21-landmark list
    in normalized [0,1] coordinates (from either legacy or tasks API).
    """

    def __init__(
        self,
        pinch_threshold: float = 0.08,           # max distance for "fingers touching"
        orchid_middle_thumb_max: float = 0.18,    # max thumb→middle-finger distance for orchid
        orchid_finger_min_spread: float = 0.15,   # min tip-to-wrist distance for spread fingers
        dwell_frames: int = 5,                    # consecutive frames to confirm a gesture
        scroll_deadzone: float = 0.015,           # dead zone for scroll activation
        scroll_gain: float = 8.0,                 # multiplier for scroll delta
    ):
        self.pinch_threshold = pinch_threshold
        self.orchid_middle_thumb_max = orchid_middle_thumb_max
        self.orchid_finger_min_spread = orchid_finger_min_spread
        self.dwell_frames = dwell_frames
        self.scroll_deadzone = scroll_deadzone
        self.scroll_gain = scroll_gain

        # State machines (frame counters for debounce)
        self._orchid_counter = 0
        self._orchid_active = False

        self._left_pinch_counter = 0
        self._left_down = False

        self._right_pinch_counter = 0
        self._right_down = False

        # Scroll state
        self._last_middle_y: Optional[float] = None

        # Debug info (last computed distances)
        self._dbg_thumb_mid_pip: float = 0.0
        self._dbg_thumb_index: float = 0.0
        self._dbg_thumb_mid_tip: float = 0.0
        self._dbg_index_spread: float = 0.0
        self._dbg_ring_spread: float = 0.0
        self._dbg_pinky_spread: float = 0.0
        self._dbg_min_spread: float = 0.0

    # ── Landmark helpers ──────────────────────────────────────────

    @staticmethod
    def _dist(a: Landmark, b: Landmark) -> float:
        dx = a.x - b.x
        dy = a.y - b.y
        return (dx * dx + dy * dy) ** 0.5

    @staticmethod
    def _dist_to_wrist(tip: Landmark, wrist: Landmark) -> float:
        """Euclidean distance from fingertip to wrist."""
        dx = tip.x - wrist.x
        dy = tip.y - wrist.y
        return (dx * dx + dy * dy) ** 0.5

    # ── Orchid-finger detection ───────────────────────────────────

    def is_orchid_pose(self, landmarks: List[Landmark]) -> bool:
        """Check if the hand is in 右手兰花指 pose.

        Conditions:
          1. Thumb tip (4) touches ANY part of the middle finger
             (tested against MCP, PIP, DIP, and TIP — min distance wins).
             In 2D projection, touching points can still appear separated
             due to depth, so we use a generous threshold.
          2. Index (8), ring (16), pinky (20) are extended away from palm
             (using an adaptive threshold based on hand size).
        """
        thumb = landmarks[THUMB_TIP]
        wrist = landmarks[WRIST]
        index_tip = landmarks[INDEX_TIP]
        ring_tip = landmarks[RING_TIP]
        pinky_tip = landmarks[PINKY_TIP]
        middle_mcp = landmarks[MIDDLE_MCP]

        # 1. Thumb close to ANY part of the middle finger
        #    Test MCP(9), PIP(10), DIP(11), TIP(12) — use minimum distance.
        #    This handles 2D projection depth ambiguity — the thumb may
        #    touch one segment of the finger while appearing near another.
        d_thumb_mid = min(
            self._dist(thumb, landmarks[MIDDLE_MCP]),
            self._dist(thumb, landmarks[MIDDLE_PIP]),
            self._dist(thumb, landmarks[MIDDLE_DIP]),
            self._dist(thumb, landmarks[MIDDLE_TIP]),
        )
        self._dbg_thumb_mid_pip = d_thumb_mid  # reuse for debug display
        if d_thumb_mid > self.orchid_middle_thumb_max:
            return False

        # 2. Adaptive threshold: use middle-finger length as reference
        hand_span = self._dist(wrist, middle_mcp) + self._dist(middle_mcp, landmarks[MIDDLE_TIP])
        min_spread = min(self.orchid_finger_min_spread, hand_span * 0.45)
        self._dbg_min_spread = min_spread

        # Index, ring, pinky must be extended away from wrist
        d_index = self._dist_to_wrist(index_tip, wrist)
        d_ring  = self._dist_to_wrist(ring_tip, wrist)
        d_pinky = self._dist_to_wrist(pinky_tip, wrist)
        self._dbg_index_spread = d_index
        self._dbg_ring_spread = d_ring
        self._dbg_pinky_spread = d_pinky

        if d_index < min_spread:
            return False
        if d_ring < min_spread:
            return False
        if d_pinky < min_spread:
            return False

        return True

    # ── Orchid activation with dwell ──────────────────────────────

    def update_orchid(self, landmarks: Optional[List[Landmark]]) -> bool:
        """Update orchid-pose dwell counter. Returns True if currently active.

        Also updates debug distances for index/middle-tip so they are
        visible on the overlay even before orchid activates.
        """
        if landmarks is None:
            self._orchid_counter = 0
            self._orchid_active = False
            return False

        # Always update debug distances (not just when orchid is on)
        self._dbg_thumb_index = self._dist(
            landmarks[INDEX_TIP], landmarks[THUMB_TIP])
        self._dbg_thumb_mid_tip = self._dist(
            landmarks[MIDDLE_TIP], landmarks[THUMB_TIP])

        if self.is_orchid_pose(landmarks):
            self._orchid_counter += 1
            if self._orchid_counter >= self.dwell_frames:
                self._orchid_active = True
        else:
            self._orchid_counter = 0
            self._orchid_active = False

        return self._orchid_active

    @property
    def is_active(self) -> bool:
        return self._orchid_active

    # ── Pinch detection (left / right click) ──────────────────────

    def detect_left_click(self, landmarks: List[Landmark]) -> Optional[str]:
        """Returns 'click' or None.

        Left click = index fingertip (8) touches thumb tip (4).
        One confirmed pinch = one clean click.

        Guard against anatomical cross-talk: bending the ring finger can
        slightly curl the index via shared tendons.  We require that the
        index finger is MORE curled than the ring finger, so ring-finger
        movement alone does not trigger a left click.
        """
        d = self._dist(landmarks[INDEX_TIP], landmarks[THUMB_TIP])
        self._dbg_thumb_index = d

        # Index must be more curled than ring finger
        d_index_wrist = self._dist_to_wrist(landmarks[INDEX_TIP], landmarks[WRIST])
        d_ring_wrist  = self._dist_to_wrist(landmarks[RING_TIP],  landmarks[WRIST])
        index_is_lead = d_index_wrist < d_ring_wrist

        return self._pinch_state_machine(
            d < self.pinch_threshold and index_is_lead,
            '_left_pinch_counter',
            '_left_down',
        )

    def detect_right_click(self, landmarks: List[Landmark]) -> Optional[str]:
        """Returns 'down', 'up', or None.

        Right click = middle fingertip (12) touches thumb tip (4).
        Short pinch → click.  Long hold → drag.  Auto-release after 3 s.
        (Distinct from orchid pose, which checks thumb→middle PIP.)
        """
        d = self._dist(landmarks[MIDDLE_TIP], landmarks[THUMB_TIP])
        self._dbg_thumb_mid_tip = d
        return self._pinch_state_machine(
            d < self.pinch_threshold,
            '_right_pinch_counter',
            '_right_down',
        )

    def _pinch_state_machine(self, is_pinching: bool,
                             counter_attr: str,
                             down_attr: str) -> Optional[str]:
        """Pinch → one clean click. No hold/drag, no release tracking.

        # --- 旧版: down/up 模式 (支持拖拽) ---
        # counter = getattr(self, counter_attr, 0)
        # is_down = getattr(self, down_attr, False)
        # if is_pinching:
        #     counter += 1
        #     setattr(self, counter_attr, counter)
        #     if counter >= self.dwell_frames and not is_down:
        #         setattr(self, down_attr, True)
        #         return 'down'
        #     if is_down and counter >= self.dwell_frames + 90:
        #         setattr(self, counter_attr, 0)
        #         setattr(self, down_attr, False)
        #         return 'up'
        # else:
        #     setattr(self, counter_attr, 0)
        #     if is_down:
        #         setattr(self, down_attr, False)
        #         return 'up'
        # return None
        """
        counter = getattr(self, counter_attr, 0)

        if is_pinching:
            counter += 1
            setattr(self, counter_attr, counter)
            if counter == self.dwell_frames:
                return 'click'
        else:
            setattr(self, counter_attr, 0)

        return None

    # ── Scroll detection ──────────────────────────────────────────

    def detect_scroll(self, landmarks: List[Landmark]) -> int:
        """Returns scroll delta (positive=up, negative=down, 0=none).

        Tracks middle fingertip (12) vertical displacement relative to
        thumb tip (4).  Requires orchid pose to be active.
        """
        thumb_y = landmarks[THUMB_TIP].y
        middle_y = landmarks[MIDDLE_TIP].y

        # Middle Y relative to thumb: larger y = lower on screen
        rel_y = middle_y - thumb_y

        if self._last_middle_y is None:
            self._last_middle_y = rel_y
            return 0

        delta = rel_y - self._last_middle_y
        self._last_middle_y = rel_y

        # Dead zone
        if abs(delta) < self.scroll_deadzone:
            return 0

        # Invert: finger moves down (positive delta) → scroll down (negative)
        scroll = int(-delta * self.scroll_gain * 120)  # 120 = one wheel notch

        return scroll

    def reset_scroll(self) -> None:
        """Reset scroll tracking (on orchid lost or mode switch)."""
        self._last_middle_y = None

    # ── Full reset ────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all state machines."""
        self._orchid_counter = 0
        self._orchid_active = False
        self._left_pinch_counter = 0
        self._left_down = False
        self._right_pinch_counter = 0
        self._right_down = False
        self.reset_scroll()

    # ── Debug info ──────────────────────────────────────────────

    def get_debug_info(self) -> dict:
        """Return a dict of last-computed distances for on-screen debug."""
        return {
            'orchid_on': self._orchid_active,
            'orchid_counter': self._orchid_counter,
            'thumb_mid_pip': round(self._dbg_thumb_mid_pip, 4),
            'thumb_mid_pip_max': self.orchid_middle_thumb_max,
            'thumb_index': round(self._dbg_thumb_index, 4),
            'thumb_mid_tip': round(self._dbg_thumb_mid_tip, 4),
            'pinch_threshold': self.pinch_threshold,
            'index_spread': round(self._dbg_index_spread, 4),
            'ring_spread': round(self._dbg_ring_spread, 4),
            'pinky_spread': round(self._dbg_pinky_spread, 4),
            'min_spread': round(self._dbg_min_spread, 4),
            'left_counter': self._left_pinch_counter,
            'right_counter': self._right_pinch_counter,
            'left_down': self._left_down,
            'right_down': self._right_down,
        }
