"""kyyy — AR Visual 9-Key Chinese Virtual Keyboard

An AR-based virtual keyboard peripheral for Windows.
Uses computer vision to detect fingertip hovering over a 9-key
phone layout and sends keystrokes system-wide via SendInput.

Usage:
    python main.py                  # Use default config.json
    python main.py --config my.json # Custom config
    python main.py --debug          # Enable debug overlays
"""

import os
import sys

# ── Pre-flight: Python version ───────────────────────────────────

_MIN_PYTHON = (3, 9)
if sys.version_info < _MIN_PYTHON:
    print(f"ERROR: Python {_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}+ required. "
          f"You are running {sys.version_info.major}.{sys.version_info.minor}.")
    sys.exit(1)

# ── Pre-flight: platform ─────────────────────────────────────────

if sys.platform != 'win32':
    print("ERROR: kyyy requires Windows (uses SendInput API).")
    print(f"       Current platform: {sys.platform}")
    sys.exit(1)

# ── Ensure src package is importable ─────────────────────────────

_proj_dir = os.path.dirname(os.path.abspath(__file__))
if _proj_dir not in sys.path:
    sys.path.insert(0, _proj_dir)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="AR 9-Key Chinese Virtual Keyboard — visual input peripheral",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
  python main.py --config my_config.json
  python main.py --debug
        """,
    )
    parser.add_argument(
        "--config", default=os.path.join(_proj_dir, "config.json"),
        help="Path to configuration file (default: config.json beside main.py)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Start with hand landmarks and debug overlays enabled"
    )
    args = parser.parse_args()

    # ── Import App here so --help works fast (no heavy deps) ──
    try:
        from src.app import App
    except ImportError as e:
        print(f"ERROR: Cannot import App. Missing dependencies? {e}")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)

    app = App(config_path=args.config)

    if args.debug:
        app._show_landmarks = True
        app._show_fps = True
        app._show_key_boundaries = True
        print("[Main] Debug mode enabled.")

    app.run()


if __name__ == "__main__":
    main()
