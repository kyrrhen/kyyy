"""Click detection with dwell-time state machine and debounce.

All timing is wall-clock-based for consistency across variable FPS.
Each key has an independent state machine; a global cooldown prevents
adjacent-fire spamming from a single hand movement.
"""

import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .overlay import KeyRect, NUM_KEYS


@dataclass
class KeyState:
    """Per-key state machine (wall-clock driven)."""
    state: str = "idle"              # idle | hovering | cooldown
    dwell_start: float = 0.0         # when fingertip entered this key
    cooldown_until: float = 0.0      # when cooldown expires


class ClickDetector:
    """Dwell-time click detection with per-key state machines.

    A click fires when the fingertip stays in the same key for at least
    `dwell_seconds` without leaving.  After firing, the key enters a
    cooldown (`debounce_seconds`) and a shorter global cooldown prevents
    adjacent keys from firing immediately.
    """

    def __init__(
        self,
        dwell_frames: int = 15,
        debounce_frames: int = 25,
        global_cooldown_seconds: float = 0.3,
        target_fps: float = 30.0,
    ):
        # Convert frame-based config to wall-clock for consistency
        self._dwell_seconds = dwell_frames / max(1.0, target_fps)
        self._debounce_seconds = debounce_frames / max(1.0, target_fps)
        self._global_cooldown = global_cooldown_seconds

        self._keys: List[KeyState] = [KeyState() for _ in range(NUM_KEYS)]
        self._global_cooldown_until: float = 0.0
        self._current_hovered: int = -1

    # ── Properties (keep frame-based getter/setter for config compat) ─

    @property
    def dwell_frames(self) -> int:
        return int(self._dwell_seconds * 30.0)

    @dwell_frames.setter
    def dwell_frames(self, val: int) -> None:
        self._dwell_seconds = max(3, val) / 30.0

    @property
    def debounce_frames(self) -> int:
        return int(self._debounce_seconds * 30.0)

    @debounce_frames.setter
    def debounce_frames(self, val: int) -> None:
        self._debounce_seconds = max(5, val) / 30.0

    # ── Main update ───────────────────────────────────────────────

    def update(
        self,
        fingertip_xy: Optional[Tuple[int, int]],
        key_rects: List[KeyRect],
        current_time: float,
    ) -> Optional[int]:
        """Process one frame. Returns the key index that triggered, or None."""
        # ── No hand ────────────────────────────────────────────────
        if fingertip_xy is None:
            self._reset_all()
            self._current_hovered = -1
            return None

        px, py = fingertip_xy

        # ── Global cooldown ────────────────────────────────────────
        if current_time < self._global_cooldown_until:
            return None

        # ── Hit-test ───────────────────────────────────────────────
        active_key = -1
        for i, rect in enumerate(key_rects):
            if rect.contains(px, py):
                active_key = i
                break
        self._current_hovered = active_key

        # ── Per-key state machines ────────────────────────────────
        triggered: Optional[int] = None

        for i, ks in enumerate(self._keys):
            hovering = (i == active_key)

            if ks.state == "idle":
                if hovering:
                    ks.state = "hovering"
                    ks.dwell_start = current_time

            elif ks.state == "hovering":
                if hovering:
                    if current_time - ks.dwell_start >= self._dwell_seconds:
                        ks.state = "cooldown"
                        ks.cooldown_until = current_time + self._debounce_seconds
                        triggered = i
                else:
                    ks.state = "idle"

            elif ks.state == "cooldown":
                if current_time >= ks.cooldown_until:
                    if hovering:
                        ks.state = "hovering"
                        ks.dwell_start = current_time
                    else:
                        ks.state = "idle"
                # else: stay cooldown

        # ── Fire & global cooldown ─────────────────────────────────
        if triggered is not None:
            self._global_cooldown_until = current_time + self._global_cooldown
            for i, ks in enumerate(self._keys):
                if i != triggered:
                    ks.state = "idle"

        return triggered

    # ── Helpers ───────────────────────────────────────────────────

    def _reset_all(self) -> None:
        for ks in self._keys:
            ks.state = "idle"

    def get_hovered_key(
        self,
        fingertip_xy: Optional[Tuple[int, int]],
        key_rects: List[KeyRect],
    ) -> int:
        """Return key index the fingertip is currently inside, or -1."""
        if fingertip_xy is None:
            return -1
        px, py = fingertip_xy
        for i, rect in enumerate(key_rects):
            if rect.contains(px, py):
                return i
        return -1

    def reset(self) -> None:
        """Reset all state (pause / resume boundary)."""
        self._reset_all()
        self._global_cooldown_until = 0.0
        self._current_hovered = -1
