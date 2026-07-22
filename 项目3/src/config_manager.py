"""Configuration manager for kyyy.

Loads / validates / saves config.json with:
- Type coercion (JSON strings → proper types)
- Range clamping for numeric values
- Color tuple validation
- Graceful fallback on corrupt or missing files
"""

import json
import os
from typing import Any, Optional, Tuple, Union


# ── Schema: key → (default, type, validator) ─────────────────────
# Validator returns the coerced value or raises ValueError.

def _clamp_range(lo: float, hi: float):
    """Return a validator that clamps numeric values to [lo, hi].

    Preserves the original type (int stays int, float stays float).
    """
    def _validator(value):
        clamped = max(lo, min(hi, value))
        # Preserve int type when possible
        if isinstance(value, int) and clamped == int(clamped):
            return int(clamped)
        return float(clamped)
    return _validator


def _coerce_int(value) -> int:
    return int(value)


def _coerce_float(value) -> float:
    return float(value)


def _coerce_bool(value) -> bool:
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value)


def _coerce_color(value):
    """Ensure a 3-element list/tuple of ints in [0, 255]."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"Expected [R,G,B] list, got {type(value).__name__}")
    return [max(0, min(255, int(v))) for v in value]


def _coerce_str(value) -> str:
    return str(value)


# Schema entries — only keys that need validation / coercion beyond default
_SCHEMA = {
    "camera_id":                (0,      _coerce_int,   None),
    "window_name":              ("",     _coerce_str,   None),
    "window_width":             (960,    _coerce_int,   _clamp_range(320, 3840)),
    "window_height":            (720,    _coerce_int,   _clamp_range(240, 2160)),
    "keyboard_alpha":           (0.25,   _coerce_float, _clamp_range(0.0, 1.0)),
    "keyboard_position":        ("left", _coerce_str,   None),
    "keyboard_size_ratio":      (0.35,   _coerce_float, _clamp_range(0.15, 0.65)),
    "keyboard_height_ratio":    (0.35,   _coerce_float, _clamp_range(0.15, 0.65)),
    "dwell_frames":             (15,     _coerce_int,   _clamp_range(3, 60)),
    "debounce_frames":          (25,     _coerce_int,   _clamp_range(5, 120)),
    "global_cooldown_seconds":  (0.3,    _coerce_float, _clamp_range(0.0, 2.0)),
    "smoothing_alpha":          (0.40,   _coerce_float, _clamp_range(0.1, 0.9)),
    "min_detection_confidence": (0.7,    _coerce_float, _clamp_range(0.3, 1.0)),
    "min_tracking_confidence":  (0.5,    _coerce_float, _clamp_range(0.3, 1.0)),
    "show_debug":               (True,   _coerce_bool,  None),
    "show_fps":                 (True,   _coerce_bool,  None),
    "show_landmarks":           (False,  _coerce_bool,  None),
    "flip_horizontal":          (True,   _coerce_bool,  None),
    "margin_px":                (6,      _coerce_int,   _clamp_range(0, 40)),
    "font_scale":               (1.0,    _coerce_float, _clamp_range(0.3, 4.0)),
    "border_thickness":         (2,      _coerce_int,   _clamp_range(1, 10)),
    "label_thickness":          (2,      _coerce_int,   _clamp_range(1, 10)),
    "pinch_threshold":          (0.06,   _coerce_float, _clamp_range(0.01, 0.5)),
    # Colors
    "key_highlight_color":      ([0, 255, 0],     _coerce_color, None),
    "key_hover_color":          ([255, 200, 60],  _coerce_color, None),
    "key_normal_color":         ([200, 200, 200], _coerce_color, None),
    "key_border_color":         ([140, 140, 140], _coerce_color, None),
    "key_text_color":           ([255, 255, 255], _coerce_color, None),
    "keyboard_bg_color":        ([20, 20, 20],    _coerce_color, None),
    # Mouse control
    "mouse_pinch_threshold":     (0.08,  _coerce_float, _clamp_range(0.02, 0.20)),
    "mouse_orchid_mid_max":      (0.18,  _coerce_float, _clamp_range(0.05, 0.35)),
    "mouse_finger_spread_min":   (0.15,  _coerce_float, _clamp_range(0.05, 0.40)),
    "mouse_dwell_frames":        (5,     _coerce_int,   _clamp_range(2, 20)),
    "mouse_scroll_deadzone":     (0.015, _coerce_float, _clamp_range(0.005, 0.05)),
    "mouse_scroll_gain":         (8.0,   _coerce_float, _clamp_range(1.0, 30.0)),
    "mouse_smoothing_alpha":     (0.30,  _coerce_float, _clamp_range(0.1, 0.9)),
    "mouse_dead_zone":           (0.002, _coerce_float, _clamp_range(0.0, 0.02)),
    "mouse_gain_x":              (1.8,   _coerce_float, _clamp_range(0.3, 5.0)),
    "mouse_gain_y":              (1.8,   _coerce_float, _clamp_range(0.3, 5.0)),
}


class ConfigManager:
    """Loads, validates, and provides typed access to config.json."""

    def __init__(self, config_path: str = "config.json"):
        self._config_path = config_path
        self._data: dict = {}
        self._build_defaults()
        self.load()

    def _build_defaults(self) -> None:
        """Build the canonical defaults dictionary from the schema."""
        self._defaults = {}
        for key, (default, _coercer, _validator) in _SCHEMA.items():
            self._defaults[key] = default

    # ── Load / Save ───────────────────────────────────────────────

    def load(self) -> None:
        """Load config from JSON. Missing file → create it. Corrupt → fallback."""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Config] Warning: Failed to parse {self._config_path}: {e}")
                loaded = {}
        else:
            print(f"[Config] File not found: {self._config_path}. Creating defaults.")
            loaded = {}

        # Merge loaded over defaults, then validate + coerce
        merged = dict(self._defaults)
        for key, value in loaded.items():
            if key in _SCHEMA:
                try:
                    merged[key] = self._coerce_value(key, value)
                except (ValueError, TypeError) as e:
                    print(f"[Config] Warning: invalid value for '{key}': {e}. "
                          f"Using default.")
            else:
                # Unknown keys pass through as-is
                merged[key] = value

        self._data = merged
        if not os.path.exists(self._config_path):
            self.save()

    def save(self) -> None:
        """Write current configuration to JSON."""
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"[Config] Error saving config: {e}")

    def reload(self) -> None:
        """Hot-reload from file."""
        print("[Config] Reloading...")
        self.load()

    # ── Coercion ──────────────────────────────────────────────────

    def _coerce_value(self, key: str, value: Any) -> Any:
        """Coerce and validate a single config value against the schema."""
        if key not in _SCHEMA:
            return value

        _default, coercer, validator = _SCHEMA[key]
        try:
            coerced = coercer(value)
        except (ValueError, TypeError):
            raise ValueError(f"cannot coerce '{value}' to required type")

        if validator is not None:
            coerced = validator(coerced)

        return coerced

    # ── Accessors ─────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key in _SCHEMA:
            value = self._coerce_value(key, value)
        self._data[key] = value

    def override(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        return key in self._data
