"""Windows keyboard event simulation via SendInput API.

Sends global keystrokes that Windows routes to the foreground
application — exactly as a physical keyboard would.
"""

import ctypes
import time
from ctypes import wintypes

from ._win32 import (
    INPUT,
    INPUT_KEYBOARD,
    KEYEVENTF_KEYUP,
    VK_1,
    VK_BACK,
    VK_RETURN,
    VK_SPACE,
    _KeyBdInput,
    _InputUnion,
    verify_input_structure,
)

# ── Key mapping (single source of truth) ─────────────────────────

# 12 keys in 3×4 grid:
# [1]  [2]  [3]
# [4]  [5]  [6]
# [7]  [8]  [9]
# [BS] [Sp] [Enter]

KEY_LABELS = ["1", "2", "3", "4", "5", "6", "7", "8", "9",
              "DEL", "SPACE", "ENTER"]

KEY_VK = [
    VK_1, VK_1 + 1, VK_1 + 2,     # 1, 2, 3
    VK_1 + 3, VK_1 + 4, VK_1 + 5, # 4, 5, 6
    VK_1 + 6, VK_1 + 7, VK_1 + 8, # 7, 8, 9
    VK_BACK,                        # Backspace
    VK_SPACE,                       # Space
    VK_RETURN,                      # Enter
]

KEY_SCAN = [
    0x02, 0x03, 0x04,  # 1, 2, 3
    0x05, 0x06, 0x07,  # 4, 5, 6
    0x08, 0x09, 0x0A,  # 7, 8, 9
    0x0E,               # Backspace
    0x39,               # Space
    0x1C,               # Enter
]

NUM_KEYS = 12


# ── KeyboardSender ───────────────────────────────────────────────

class KeyboardSender:
    """Sends global keyboard events using the Windows SendInput API."""

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._extra  = ctypes.c_ulong(0)
        verify_input_structure()

    def send_key(self, key_index: int) -> bool:
        """Send a single key-down + key-up sequence for key index 0-11."""
        if not (0 <= key_index < NUM_KEYS):
            print(f"[KeySender] Invalid key index: {key_index}")
            return False

        vk = KEY_VK[key_index]
        scan = KEY_SCAN[key_index]

        try:
            self._press(vk, scan)
            return True
        except Exception as e:
            print(f"[KeySender] Error sending {KEY_LABELS[key_index]}: {e}")
            return False

    def _press(self, vk: int, scan: int) -> None:
        down = self._make_input(vk, scan, 0)
        up   = self._make_input(vk, scan, KEYEVENTF_KEYUP)
        c_send = self._user32.SendInput
        c_send(1, ctypes.byref(down), ctypes.sizeof(down))
        time.sleep(0.02)
        c_send(1, ctypes.byref(up), ctypes.sizeof(up))

    def _make_input(self, vk: int, scan: int, flags: int) -> INPUT:
        ki = _KeyBdInput(
            wintypes.WORD(vk),
            wintypes.WORD(scan),
            wintypes.DWORD(flags),
            wintypes.DWORD(0),
            ctypes.pointer(self._extra),
        )
        union = _InputUnion()
        union.ki = ki
        inp = INPUT()
        inp.type = wintypes.DWORD(INPUT_KEYBOARD)
        inp.union = union
        return inp


# ── Quick self-test ──────────────────────────────────────────────

if __name__ == "__main__":
    print("KeyboardSender self-test — switch to Notepad in 3 seconds...")
    time.sleep(3)
    sender = KeyboardSender()
    for idx in (0, 1, 2, 10):
        sender.send_key(idx)
        time.sleep(0.1)
    print("Done. Check the text editor for '123 '.")
