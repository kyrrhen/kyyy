"""Shared Windows API ctypes definitions.

Used by both keyboard_sender.py and mouse_controller.py.
Single source of truth for INPUT structure layout to prevent
definition drift between the two senders.
"""

import ctypes
import sys
from ctypes import wintypes

# ── Constants ────────────────────────────────────────────────────

INPUT_MOUSE    = 0
INPUT_KEYBOARD = 1

# Keyboard flags
KEYEVENTF_KEYUP   = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_UNICODE  = 0x0004

# Mouse flags
MOUSEEVENTF_MOVE       = 0x0001
MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_RIGHTDOWN  = 0x0008
MOUSEEVENTF_RIGHTUP    = 0x0010
MOUSEEVENTF_ABSOLUTE   = 0x8000
MOUSEEVENTF_WHEEL      = 0x0800
MOUSEEVENTF_HWHEEL     = 0x01000

# Virtual-key codes (ASCII-range subset)
VK_BACK   = 0x08
VK_RETURN = 0x0D
VK_SPACE  = 0x20
VK_1      = 0x31

# ── SendInput structures ─────────────────────────────────────────

class _KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk",         wintypes.WORD),
        ("wScan",       wintypes.WORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx",          wintypes.LONG),
        ("dy",          wintypes.LONG),
        ("mouseData",   wintypes.DWORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg",    wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [
        ("ki", _KeyBdInput),
        ("mi", _MouseInput),
        ("hi", _HardwareInput),
    ]


class INPUT(ctypes.Structure):
    """The Windows INPUT structure (SendInput's argument type)."""
    _fields_ = [
        ("type",  wintypes.DWORD),
        ("union", _InputUnion),
    ]


# ── Structure size verification ──────────────────────────────────

_EXPECTED = {(32, "WindowsPE"): 28, (64, "WindowsPE"): 40}


def verify_input_structure() -> bool:
    """Verify INPUT structure size matches the platform ABI.

    Returns True if OK, False if mismatch (warning is printed).
    """
    bits = 64 if sys.maxsize > 2**32 else 32
    actual = ctypes.sizeof(INPUT)
    expected = _EXPECTED.get((bits, "WindowsPE"))
    if expected is None:
        print(f"[Win32] Warning: unknown platform {bits}-bit, "
              f"sizeof(INPUT)={actual}")
        return True  # not a hard error
    if actual != expected:
        print(f"[Win32] WARNING: sizeof(INPUT)={actual}, "
              f"expected {expected} ({bits}-bit). "
              f"Input events may malfunction.")
        return False
    return True
