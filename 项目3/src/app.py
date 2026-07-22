"""Main application orchestrator for kyyy.

Integrates keyboard mode (9-key T9) and mouse mode (gesture cursor)
into a single application.  Mode switch via M key.
"""

import sys
import time
from typing import Optional

import cv2
import numpy as np

from .camera import CameraManager
from .click_detector import ClickDetector
from .config_manager import ConfigManager
from .coord_mapper import CoordMapper
from .gesture_detector import GestureDetector, MIDDLE_MCP
from .hand_detector import HandDetector
from .keyboard_sender import KeyboardSender, KEY_LABELS
from .mouse_controller import MouseController
from .overlay import OverlayRenderer

_MIN_PYTHON = (3, 9)


class App:
    """AR 9-Key Virtual Keyboard + Gesture Mouse."""

    def __init__(self, config_path: str = "config.json"):
        if sys.version_info < _MIN_PYTHON:
            print(f"[App] ERROR: Python {sys.version_info.major}."
                  f"{sys.version_info.minor} detected. Requires Python 3.9+.")
            sys.exit(1)

        self._config = ConfigManager(config_path)
        self._running = False
        self._paused = False
        self._mode = "keyboard"  # "keyboard" | "mouse"

        # ── Shared modules ─────────────────────────────────────

        self._camera = CameraManager(
            camera_id=self._config.get("camera_id", 0),
            flip_horizontal=self._config.get("flip_horizontal", True),
        )

        self._hand_detector = HandDetector(
            min_detection_confidence=self._config.get("min_detection_confidence", 0.7),
            min_tracking_confidence=self._config.get("min_tracking_confidence", 0.5),
            smoothing_alpha=self._config.get("smoothing_alpha", 0.40),
        )

        # ── Keyboard modules ───────────────────────────────────

        self._click_detector = ClickDetector(
            dwell_frames=self._config.get("dwell_frames", 15),
            debounce_frames=self._config.get("debounce_frames", 25),
            global_cooldown_seconds=self._config.get("global_cooldown_seconds", 0.3),
        )
        self._keyboard_sender = KeyboardSender()

        self._overlay = OverlayRenderer(
            keyboard_alpha=self._config.get("keyboard_alpha", 0.25),
            keyboard_position=self._config.get("keyboard_position", "left"),
            keyboard_size_ratio=self._config.get("keyboard_size_ratio", 0.35),
            margin_px=self._config.get("margin_px", 6),
            key_normal_color=tuple(self._config.get("key_normal_color", [200, 200, 200])),
            key_hover_color=tuple(self._config.get("key_hover_color", [255, 200, 60])),
            key_highlight_color=tuple(self._config.get("key_highlight_color", [0, 255, 0])),
            key_border_color=tuple(self._config.get("key_border_color", [140, 140, 140])),
            key_text_color=tuple(self._config.get("key_text_color", [255, 255, 255])),
            keyboard_bg_color=tuple(self._config.get("keyboard_bg_color", [20, 20, 20])),
            font_scale=self._config.get("font_scale", 1.0),
            border_thickness=self._config.get("border_thickness", 2),
            label_thickness=self._config.get("label_thickness", 2),
        )

        # ── Mouse modules ──────────────────────────────────────

        self._gesture_detector = GestureDetector(
            pinch_threshold=self._config.get("mouse_pinch_threshold", 0.06),
            orchid_middle_thumb_max=self._config.get("mouse_orchid_mid_max", 0.08),
            orchid_finger_min_spread=self._config.get("mouse_finger_spread_min", 0.15),
            dwell_frames=self._config.get("mouse_dwell_frames", 5),
            scroll_deadzone=self._config.get("mouse_scroll_deadzone", 0.015),
            scroll_gain=self._config.get("mouse_scroll_gain", 8.0),
        )

        self._coord_mapper = CoordMapper(
            smoothing_alpha=self._config.get("mouse_smoothing_alpha", 0.30),
            dead_zone=self._config.get("mouse_dead_zone", 0.002),
            gain_x=self._config.get("mouse_gain_x", 1.8),
            gain_y=self._config.get("mouse_gain_y", 1.8),
        )

        self._mouse_controller = MouseController()

        # ── Display state ──────────────────────────────────────

        self._window_name = self._config.get("window_name", "kyyy")
        self._triggered_key: Optional[int] = None
        self._triggered_flash_frames: int = 0
        self._show_fps = self._config.get("show_fps", True)
        self._show_landmarks = self._config.get("show_landmarks", False)
        self._show_key_boundaries = False

        # FPS
        self._fps = 0.0
        self._fps_alpha = 0.1

        # Mouse state display
        self._orchid_on = False
        # self._left_down = False     # 拖拽模式时启用
        # self._right_down = False
        self._cursor_pos: Optional[tuple] = None

    # ══════════════════════════════════════════════════════════════
    #  MAIN LOOP
    # ══════════════════════════════════════════════════════════════

    def run(self) -> None:
        self._print_banner()
        self._camera.open()

        cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL)
        cv2.resizeWindow(self._window_name,
                         self._config.get("window_width", 960),
                         self._config.get("window_height", 720))

        self._running = True
        print(f"[App] Mode: {self._mode.upper()}.  M = switch mode.  Q = quit.")

        while self._running:
            if not self._window_is_open():
                print("[App] Window closed by user.")
                break

            if self._mode == "keyboard":
                self._tick_keyboard()
            else:
                self._tick_mouse()

        self._shutdown()

    # ══════════════════════════════════════════════════════════════
    #  KEYBOARD MODE TICK
    # ══════════════════════════════════════════════════════════════

    def _tick_keyboard(self) -> None:
        loop_start = time.time()

        success, frame = self._camera.read()
        if not success:
            self._handle_key(cv2.waitKey(50) & 0xFF)
            # Show placeholder
            ph = self._make_placeholder()
            if ph is not None:
                cv2.imshow(self._window_name, ph)
            return

        fh, fw = frame.shape[:2]
        key_rects = self._overlay.compute_key_rects(fw, fh)

        fingertip_xy = None
        if not self._paused:
            fingertip_xy = self._hand_detector.detect(frame)

        triggered = None
        if not self._paused:
            triggered = self._click_detector.update(
                fingertip_xy, key_rects, time.time())

        if triggered is not None:
            self._keyboard_sender.send_key(triggered)
            self._triggered_key = triggered
            self._triggered_flash_frames = 8

        hovered = -1
        if fingertip_xy is not None:
            hovered = self._click_detector.get_hovered_key(fingertip_xy, key_rects)

        display_triggered = (self._triggered_key
                             if self._triggered_flash_frames > 0 else -1)
        display_frame = self._overlay.render(
            frame, key_rects, hovered, display_triggered,
            show_key_boundaries=self._show_key_boundaries)

        if self._triggered_flash_frames > 0:
            self._triggered_flash_frames -= 1
            if self._triggered_flash_frames == 0:
                self._triggered_key = None

        if self._show_landmarks and not self._paused:
            self._hand_detector.draw_landmarks(display_frame)
        if fingertip_xy is not None:
            self._overlay.draw_fingertip(display_frame, fingertip_xy)

        self._draw_hud(display_frame, loop_start, hovered)
        cv2.imshow(self._window_name, display_frame)
        self._handle_key(cv2.waitKey(5) & 0xFF)

    # ══════════════════════════════════════════════════════════════
    #  MOUSE MODE TICK
    # ══════════════════════════════════════════════════════════════

    def _tick_mouse(self) -> None:
        loop_start = time.time()

        success, frame = self._camera.read()
        if not success:
            self._handle_key(cv2.waitKey(50) & 0xFF)
            ph = self._make_placeholder()
            if ph is not None:
                cv2.imshow(self._window_name, ph)
            return

        # ── Detect hand ─────────────────────────────────────────
        if not self._paused:
            fingertip_xy = self._hand_detector.detect(frame)
        else:
            fingertip_xy = None

        # ── Gesture detection ───────────────────────────────────
        landmarks = None
        if not self._paused:
            landmarks = self._hand_detector._get_all_landmarks()
            prev_orchid = self._orchid_on
            self._orchid_on = self._gesture_detector.update_orchid(landmarks)

            # Console log on state changes
            if self._orchid_on and not prev_orchid:
                print("[Mouse] 🟢 兰花指激活 — 鼠标控制中")
            elif not self._orchid_on and prev_orchid:
                print("[Mouse] 🔴 兰花指丢失 — 暂停控制")

            if self._orchid_on and landmarks is not None:

                # ── 右键 (已禁用) ──────────────────────────────
                # rc = self._gesture_detector.detect_right_click(landmarks)
                # if rc == 'down':
                #     self._mouse_controller.right_down()
                # elif rc == 'up':
                #     self._mouse_controller.right_up()

                # ── 左键点击 ────────────────────────────────────
                lc = self._gesture_detector.detect_left_click(landmarks)
                if lc == 'click':
                    print("[Mouse] 左键点击")
                    self._mouse_controller.left_click()

                # ── 滚轮 (已禁用) ──────────────────────────────
                # scroll = self._gesture_detector.detect_scroll(landmarks)
                # if scroll != 0:
                #     self._mouse_controller.scroll(scroll)

                # ── 光标移动 ────────────────────────────────────
                palm_center = landmarks[MIDDLE_MCP]
                pos = self._coord_mapper.map_to_screen(palm_center.x, palm_center.y)
                if pos is not None:
                    self._cursor_pos = pos
                    sw, sh = self._coord_mapper.screen_size
                    self._mouse_controller.move(pos[0], pos[1], sw, sh)
            else:
                # ── 兰花指丢失 → 释放 (已禁用，click 模式无需) ──
                # if self._left_down: ...
                self._gesture_detector.reset_scroll()

        # ── Every 60 frames, print debug summary ────────────────
        if not hasattr(self, '_mouse_frame_count'):
            self._mouse_frame_count = 0
        self._mouse_frame_count += 1
        if self._mouse_frame_count % 60 == 0:
            dbg = self._gesture_detector.get_debug_info()
            hand_str = "有手" if landmarks is not None else "无手"
            print(f"[Mouse] f#{self._mouse_frame_count} | {hand_str} | "
                  f"Orchid={'ON' if dbg['orchid_on'] else 'off'}"
                  f"({dbg['orchid_counter']}) | "
                  f"Th-PIP={dbg['thumb_mid_pip']}/{dbg['thumb_mid_pip_max']} | "
                  f"Th-Idx={dbg['thumb_index']} Th-MidTip={dbg['thumb_mid_tip']} | "
                  f"Spread={dbg['index_spread']}/{dbg['ring_spread']}/{dbg['pinky_spread']}")

        # ── Render ──────────────────────────────────────────────
        display_frame = frame.copy()
        self._draw_mouse_overlay(display_frame, landmarks)

        if self._show_landmarks and not self._paused:
            self._hand_detector.draw_landmarks(display_frame)
        if fingertip_xy is not None:
            self._overlay.draw_fingertip(display_frame, fingertip_xy)

        self._draw_hud(display_frame, loop_start, hovered_key=-1)
        cv2.imshow(self._window_name, display_frame)
        self._handle_key(cv2.waitKey(5) & 0xFF)

    def _draw_mouse_overlay(self, frame: np.ndarray,
                            landmarks=None) -> None:
        """Draw mouse-mode indicators on the frame."""
        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX

        # ── 1. Hand detection status (top-left, BIG) ────────────
        hand_ok = landmarks is not None
        if hand_ok:
            hand_text = "手: 检测到"
            hand_color = (0, 255, 0)
        else:
            hand_text = "手: 未检测到"
            hand_color = (0, 0, 255)  # RED — very visible
        cv2.putText(frame, hand_text, (10, 35), font, 0.8, hand_color, 2, cv2.LINE_AA)

        # ── 2. Orchid status (top-left, below hand) ─────────────
        dbg = self._gesture_detector.get_debug_info()
        if self._orchid_on:
            orch_text = "兰花指: OK -> 鼠标活动!"
            orch_color = (0, 255, 0)
        else:
            orch_text = f"兰花指: 等待... ({dbg['orchid_counter']}/{self._gesture_detector.dwell_frames})"
            orch_color = (0, 200, 255) if dbg['orchid_counter'] > 0 else (150, 150, 150)
        cv2.putText(frame, orch_text, (10, 65), font, 0.7, orch_color, 2, cv2.LINE_AA)

        # ── 3. Distance debug (left side, below status) ─────────
        dbg_x = 10
        dbg_y = 85
        fs = 0.45
        thk = 1

        # Helper to color-code pass/fail
        def _ok(v, limit):
            return (0, 220, 0) if v <= limit else (100, 100, 255)

        lines = [
            (f"Thumb->PIP:  {dbg['thumb_mid_pip']:.3f}  (需<{dbg['thumb_mid_pip_max']})",
             _ok(dbg['thumb_mid_pip'], dbg['thumb_mid_pip_max'])),
            (f"Thumb->Idx:  {dbg['thumb_index']:.3f}  (需<{dbg['pinch_threshold']})",
             _ok(dbg['thumb_index'], dbg['pinch_threshold'])),
            (f"Thumb->MidTip:{dbg['thumb_mid_tip']:.3f}  (需<{dbg['pinch_threshold']})",
             _ok(dbg['thumb_mid_tip'], dbg['pinch_threshold'])),
            (f"Spread I/R/P: {dbg['index_spread']:.3f}/{dbg['ring_spread']:.3f}/{dbg['pinky_spread']:.3f}",
             (200, 200, 200)),
            (f"  minSpread: {dbg['min_spread']:.3f}",
             (200, 200, 200) if all(v >= dbg['min_spread'] for v in
                [dbg['index_spread'], dbg['ring_spread'], dbg['pinky_spread']])
             else (100, 100, 255)),
            (f"Click Lc:{dbg['left_counter']}  (dwell={self._gesture_detector.dwell_frames})",
             (255, 255, 180)),
            # (f"Btn L:{'DN' if dbg['left_down'] else 'up'} "   # 拖拽模式时启用
            #  f"R:{'DN' if dbg['right_down'] else 'up'}  "
            #  f"Lc:{dbg['left_counter']} Rc:{dbg['right_counter']}",
            #  (255, 255, 180)),
        ]
        for i, (text, color) in enumerate(lines):
            cv2.putText(frame, text, (dbg_x, dbg_y + i * 17), font, fs, color, thk, cv2.LINE_AA)

        # ── 4. Mouse status (top-right) ─────────────────────────
        if self._orchid_on:
            color = (0, 255, 0)
            text = "MOUSE ACTIVE"
        else:
            color = (100, 100, 100)
            text = "兰花指待机..."
        (tw, th), _ = cv2.getTextSize(text, font, 0.7, 2)
        cv2.putText(frame, text, (w - tw - 10, 30), font, 0.7, color, 2, cv2.LINE_AA)

        # if self._orchid_on:                                     # 拖拽模式时启用
        #     btn_y = 55
        #     lc_text = "L:DOWN" if self._left_down else "L:up"
        #     rc_text = "R:DOWN" if self._right_down else "R:up"
        #     ...

        if self._orchid_on and self._cursor_pos is not None:
            norm = self._coord_mapper.get_smoothed_norm()
            if norm is not None:
                cx = int(norm[0] * w)
                cy = int(norm[1] * h)
                ch_len = 15
                cv2.line(frame, (cx - ch_len, cy), (cx + ch_len, cy),
                         (0, 255, 255), 2, cv2.LINE_AA)
                cv2.line(frame, (cx, cy - ch_len), (cx, cy + ch_len),
                         (0, 255, 255), 2, cv2.LINE_AA)
                cv2.circle(frame, (cx, cy), 6, (0, 255, 255), 2, cv2.LINE_AA)

    # ══════════════════════════════════════════════════════════════
    #  SHARED UI
    # ══════════════════════════════════════════════════════════════

    def _draw_hud(self, frame: np.ndarray, loop_start: float,
                  hovered_key: int) -> None:
        """Draw FPS + status bar (shared across modes)."""
        elapsed = time.time() - loop_start
        instant_fps = 1.0 / elapsed if elapsed > 0 else 0
        self._fps = (self._fps_alpha * instant_fps +
                     (1 - self._fps_alpha) * self._fps)

        if self._show_fps:
            self._draw_fps(frame)

        self._draw_status_bar(frame, hovered_key)

    def _draw_fps(self, frame: np.ndarray) -> None:
        fps_text = f"FPS: {self._fps:.1f}"
        cv2.putText(frame, fps_text, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

    def _draw_status_bar(self, frame: np.ndarray, hovered_key: int) -> None:
        h = frame.shape[0]
        y = h - 10
        parts = []

        # Mode
        mode_str = "[KEYBOARD]" if self._mode == "keyboard" else "[MOUSE]"
        parts.append(mode_str)

        if self._paused:
            parts.append("[PAUSED]")
        if not self._camera.connected:
            parts.append("[NO CAM]")
        if self._mode == "keyboard" and hovered_key >= 0:
            parts.append(f"Hover: {KEY_LABELS[hovered_key]}")
        if self._mode == "mouse" and self._orchid_on:
            parts.append("兰花指 ✓")

        status = " ".join(parts)
        cv2.putText(frame, status, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)

    # ══════════════════════════════════════════════════════════════
    #  CONTROLS
    # ══════════════════════════════════════════════════════════════

    def _handle_key(self, key: int) -> None:
        if key == 0:
            return
        ch = chr(key).lower() if 32 <= key < 127 else ""

        if key == 27 or ch == 'q':
            self._running = False
            print("[App] Quit requested.")

        elif ch == 'm':
            self._switch_mode()

        elif ch == 'p':
            self._paused = not self._paused
            state = "PAUSED" if self._paused else "RESUMED"
            print(f"[App] Detection {state}.")
            self._click_detector.reset()
            self._gesture_detector.reset()

        elif ch == '+' or ch == '=':
            new_alpha = min(1.0, self._overlay.keyboard_alpha + 0.05)
            self._overlay.keyboard_alpha = new_alpha
            self._config.set("keyboard_alpha", new_alpha)
            print(f"[App] Keyboard alpha: {new_alpha:.2f}")

        elif ch == '-':
            new_alpha = max(0.05, self._overlay.keyboard_alpha - 0.05)
            self._overlay.keyboard_alpha = new_alpha
            self._config.set("keyboard_alpha", new_alpha)
            print(f"[App] Keyboard alpha: {new_alpha:.2f}")

        elif ch == ']':
            if self._mode == "keyboard":
                v = self._click_detector.dwell_frames + 2
                self._click_detector.dwell_frames = v
                print(f"[App] Dwell: {v}")
            else:
                v = min(5.0, self._coord_mapper.gain_x + 0.1)
                self._coord_mapper.gain_x = v
                self._coord_mapper.gain_y = v
                print(f"[App] Mouse gain: {v:.1f}")

        elif ch == '[':
            if self._mode == "keyboard":
                v = max(3, self._click_detector.dwell_frames - 2)
                self._click_detector.dwell_frames = v
                print(f"[App] Dwell: {v}")
            else:
                v = max(0.3, self._coord_mapper.gain_x - 0.1)
                self._coord_mapper.gain_x = v
                self._coord_mapper.gain_y = v
                print(f"[App] Mouse gain: {v:.1f}")

        elif ch == 'd':
            self._show_landmarks = not self._show_landmarks
            print(f"[App] Landmarks: {'ON' if self._show_landmarks else 'OFF'}")

        elif ch == 'f':
            self._show_fps = not self._show_fps
            print(f"[App] FPS: {'ON' if self._show_fps else 'OFF'}")

        elif ch == 'b':
            self._show_key_boundaries = not self._show_key_boundaries
            print(f"[App] Key bounds: {'ON' if self._show_key_boundaries else 'OFF'}")

        elif ch == 'r':
            self._config.reload()
            self._apply_config()
            print("[App] Config reloaded.")

    def _switch_mode(self) -> None:
        """Toggle between keyboard and mouse modes."""
        if self._mode == "keyboard":
            self._mode = "mouse"
            self._click_detector.reset()
            self._coord_mapper.reset()
            print("[App] >>> Switched to MOUSE mode")
            print("[App]     Make 兰花指 (thumb+mid touch, others spread)")
        else:
            self._mode = "keyboard"
            self._gesture_detector.reset()
            # if self._left_down:                         # 拖拽模式时启用
            #     self._mouse_controller.left_up()
            #     self._left_down = False
            # if self._right_down:
            #     self._mouse_controller.right_up()
            #     self._right_down = False
            print("[App] >>> Switched to KEYBOARD mode")

    def _apply_config(self) -> None:
        """Push config to live modules."""
        # Keyboard
        self._overlay.keyboard_alpha = self._config.get("keyboard_alpha", 0.25)
        self._overlay.position = self._config.get("keyboard_position", "left")
        self._overlay.size_ratio = self._config.get("keyboard_size_ratio", 0.35)
        self._click_detector.dwell_frames = self._config.get("dwell_frames", 15)
        self._click_detector.debounce_frames = self._config.get("debounce_frames", 25)
        # Mouse
        self._gesture_detector.pinch_threshold = self._config.get("mouse_pinch_threshold", 0.08)
        self._coord_mapper.gain_x = self._config.get("mouse_gain_x", 1.8)
        self._coord_mapper.gain_y = self._config.get("mouse_gain_y", 1.8)
        self._coord_mapper.smoothing_alpha = self._config.get("mouse_smoothing_alpha", 0.30)

    # ══════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════

    def _window_is_open(self) -> bool:
        try:
            prop = cv2.getWindowProperty(self._window_name, cv2.WND_PROP_VISIBLE)
            return prop >= 0
        except cv2.error:
            return False

    def _make_placeholder(self) -> Optional[np.ndarray]:
        w = min(self._config.get("window_width", 960), 1280)
        h = min(self._config.get("window_height", 720), 720)
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        msg = "Camera Unavailable"
        sub = "Press R to retry  |  Q to quit"
        (mw, mh), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)
        (sw, sh), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.putText(frame, msg,
                    (w // 2 - mw // 2, h // 2 - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 255), 3, cv2.LINE_AA)
        cv2.putText(frame, sub,
                    (w // 2 - sw // 2, h // 2 + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 150, 150), 2, cv2.LINE_AA)
        return frame

    def _print_banner(self) -> None:
        print()
        print("=" * 58)
        print("  kyyy — AR Input Suite (Keyboard + Mouse)")
        print("=" * 58)
        print(f"  Python {sys.version_info.major}.{sys.version_info.minor}"
              f".{sys.version_info.micro}  |  OpenCV {cv2.__version__}")
        print("-" * 58)
        print("  M            Switch mode     P       Pause")
        print("  +/-          Transparency    [ ]     Sensitivity")
        print("  D            Landmarks       F       FPS")
        print("  Q / ESC      Quit            R       Reload config")
        print("-" * 58)
        print("  Keyboard mode: hover finger over keys → dwell to type")
        print("  Mouse mode:    兰花指 → cursor control, pinch = click")
        print("=" * 58)
        print()

    def _shutdown(self) -> None:
        print("[App] Shutting down...")
        # if self._left_down: self._mouse_controller.left_up()   # 拖拽模式时启用
        # if self._right_down: self._mouse_controller.right_up()
        try:
            self._hand_detector.release()
        except Exception as e:
            print(f"[App] Error releasing hand detector: {e}")
        try:
            self._camera.release()
        except Exception as e:
            print(f"[App] Error releasing camera: {e}")
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        try:
            self._config.save()
        except Exception:
            pass
        print("[App] Goodbye.")
