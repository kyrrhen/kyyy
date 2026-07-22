"""Windows mouse event simulation via SendInput API.

Sends global mouse events — move, button down/up, scroll — that
Windows routes to the foreground application, just like a physical
mouse would.
"""

import ctypes
import time
from ctypes import wintypes

from ._win32 import (
    INPUT,
    INPUT_MOUSE,
    MOUSEEVENTF_ABSOLUTE,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_MOVE,
    MOUSEEVENTF_RIGHTDOWN,
    MOUSEEVENTF_RIGHTUP,
    MOUSEEVENTF_WHEEL,
    _InputUnion,
    _MouseInput,
    verify_input_structure,
)

WHEEL_DELTA = 120  # one scroll notch


# ── Coordinate normalization ─────────────────────────────────────

def _norm(pixel: int, dimension: int) -> int:
    """Convert pixel coordinate to Windows absolute range [0, 65535]."""
    return int(pixel * 65535 / max(1, dimension))


# ── MouseController ──────────────────────────────────────────────

class MouseController:
    """Sends global mouse events via Win32 SendInput."""

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._extra  = ctypes.c_ulong(0)
        verify_input_structure()

    # ── Move ──────────────────────────────────────────────────

    def move(self, screen_x: int, screen_y: int,
             screen_w: int = 1920, screen_h: int = 1080) -> None:
        """Move cursor to absolute screen position."""
        nx = _norm(screen_x, screen_w)
        ny = _norm(screen_y, screen_h)

        mi = _MouseInput(
            wintypes.LONG(nx), wintypes.LONG(ny),
            wintypes.DWORD(0),
            wintypes.DWORD(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE),
            wintypes.DWORD(0), ctypes.pointer(self._extra),
        )
        self._send(mi)

    # ── Buttons ───────────────────────────────────────────────

    def left_down(self) -> None:
        self._button(MOUSEEVENTF_LEFTDOWN)

    def left_up(self) -> None:
        self._button(MOUSEEVENTF_LEFTUP)

    def left_click(self) -> None:
        self.left_down()
        time.sleep(0.03)
        self.left_up()

    def right_down(self) -> None:
        self._button(MOUSEEVENTF_RIGHTDOWN)

    def right_up(self) -> None:
        self._button(MOUSEEVENTF_RIGHTUP)

    def right_click(self) -> None:
        self.right_down()
        time.sleep(0.03)
        self.right_up()

    # ── Scroll ────────────────────────────────────────────────

    def scroll(self, amount: int) -> None:
        """Scroll vertically. Positive=up, negative=down. 120 = 1 notch."""
        mi = _MouseInput(
            wintypes.LONG(0), wintypes.LONG(0),
            wintypes.DWORD(amount), wintypes.DWORD(MOUSEEVENTF_WHEEL),
            wintypes.DWORD(0), ctypes.pointer(self._extra),
        )
        self._send(mi)

    # ── Helpers ───────────────────────────────────────────────

    def _button(self, flag: int) -> None:
        mi = _MouseInput(
            wintypes.LONG(0), wintypes.LONG(0),
            wintypes.DWORD(0), wintypes.DWORD(flag),
            wintypes.DWORD(0), ctypes.pointer(self._extra),
        )
        self._send(mi)

    def _send(self, mi: _MouseInput) -> None:
        union = _InputUnion()
        union.mi = mi
        inp = INPUT()
        inp.type = wintypes.DWORD(INPUT_MOUSE)
        inp.union = union
        self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


# ── Quick test ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("MouseController test — moving cursor in a square...")
    mc = MouseController()
    sw = mc._user32.GetSystemMetrics(0)
    sh = mc._user32.GetSystemMetrics(1)
    print(f"  Screen: {sw}x{sh}")
    steps = [(sw//3, sh//3), (2*sw//3, sh//3),
             (2*sw//3, 2*sh//3), (sw//3, 2*sh//3), (sw//3, sh//3)]
    for x, y in steps:
        mc.move(x, y, sw, sh)
        time.sleep(0.5)
    print("  Done.")
