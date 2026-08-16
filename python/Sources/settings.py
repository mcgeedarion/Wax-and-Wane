#!/usr/bin/env python3
"""Settings module for Wax and Wane.

Handles configuration loading, validation, and CLI argument parsing.
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Settings:
    """Configuration settings for Wax and Wane brightness control."""
    
    poll_interval_sec: float = 2.0
    smoothing_window: int = 5
    camera_index: int = 0
    capture_frames: int = 3
    change_threshold: float = 0.02
    rise_threshold: Optional[float] = None
    fall_threshold: Optional[float] = None
    min_update_interval_sec: float = 0.0

    ambient_dark: float = 0.0
    ambient_bright: float = 1.0
    output_gamma: float = 1.0

    keyboard_min: float = 0.0
    keyboard_max: float = 1.0
    invert_keyboard: bool = False
    keyboard_control: str = "auto"
    manual_keyboard_brightness: float = 0.5
    keyboard_backend: Optional[str] = None

    screen_min: float = 0.2
    screen_max: float = 1.0
    invert_screen: bool = False
    screen_control: str = "auto"
    manual_screen_brightness: float = 0.7
    screen_backend: Optional[str] = None

    default_keyboard_brightness: float = 0.5
    default_screen_brightness: float = 0.7
    restore_original_brightness: bool = True
    dry_run: bool = False

    max_runtime_sec: float = 3600.0
    reminder_interval_sec: float = 900.0


def load_config(path: str) -> dict:
    """Load a JSON config file and return its contents as a dict.
    
    Args:
        path: Path to JSON configuration file.
        
    Returns:
        Dictionary containing configuration values.
        
    Raises:
        ValueError: If config file is not a valid JSON object.
    """
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must be a JSON object, got {type(data).__name__}")
    unknown = set(data) - set(asdict(Settings()).keys())
    if unknown:
        import logging
        logging.warning("Unknown config keys (ignored): %s", ", ".join(sorted(unknown)))
    return data


def validate_settings(s: Settings) -> None:
    """Validate settings object for correctness.
    
    Args:
        s: Settings object to validate.
        
    Raises:
        ValueError: If any setting is invalid.
    """
    def check(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    def unit(value: float, name: str) -> None:
        check(0.0 <= value <= 1.0, f"{name} must be in [0, 1]")

    check(s.poll_interval_sec > 0, "poll_interval_sec must be > 0")
    check(s.smoothing_window > 0, "smoothing_window must be > 0")
    check(s.camera_index >= 0, "camera_index must be >= 0")
    check(s.capture_frames > 0, "capture_frames must be > 0")
    check(s.change_threshold >= 0, "change_threshold must be >= 0")
    if s.rise_threshold is not None:
        check(s.rise_threshold >= 0, "rise_threshold must be >= 0")
    if s.fall_threshold is not None:
        check(s.fall_threshold >= 0, "fall_threshold must be >= 0")
    check(s.min_update_interval_sec >= 0, "min_update_interval_sec must be >= 0")
    unit(s.ambient_dark, "ambient_dark")
    unit(s.ambient_bright, "ambient_bright")
    check(s.ambient_bright > s.ambient_dark, "ambient_bright must be greater than ambient_dark")
    check(s.output_gamma > 0, "output_gamma must be > 0")
    check(s.output_gamma <= 10.0, "output_gamma must be <= 10.0")
    unit(s.keyboard_min, "keyboard_min")
    unit(s.keyboard_max, "keyboard_max")
    check(s.keyboard_min <= s.keyboard_max, "keyboard_min must be <= keyboard_max")
    unit(s.manual_keyboard_brightness, "manual_keyboard_brightness")
    unit(s.default_keyboard_brightness, "default_keyboard_brightness")
    unit(s.screen_min, "screen_min")
    unit(s.screen_max, "screen_max")
    check(s.screen_min <= s.screen_max, "screen_min must be <= screen_max")
    unit(s.manual_screen_brightness, "manual_screen_brightness")
    unit(s.default_screen_brightness, "default_screen_brightness")
    check(s.keyboard_control in {"auto", "manual", "system"}, 
          "keyboard_control must be one of: auto, manual, system")
    check(s.screen_control in {"auto", "manual", "system"}, 
          "screen_control must be one of: auto, manual, system")
    check(s.max_runtime_sec >= 0, "max_runtime_sec must be >= 0")
    check(s.reminder_interval_sec >= 0, "reminder_interval_sec must be >= 0")


def default_config_json() -> str:
    """Return default configuration as formatted JSON string."""
    return json.dumps(asdict(Settings()), indent=2, sort_keys=True)


def build_settings(args: argparse.Namespace) -> Settings:
    """Merge JSON config (if given) with CLI overrides into a Settings object.
    
    Priority: CLI flags > JSON config > built-in defaults.
    
    Args:
        args: Parsed command-line arguments.
        
    Returns:
        Settings object with merged configuration.
    """
    s = Settings()

    if args.config:
        cfg = load_config(args.config)
        for key, value in cfg.items():
            if hasattr(s, key):
                current = getattr(s, key)
                if current is None:
                    hints = Settings.__dataclass_fields__
                    if key in hints:
                        ann = hints[key].type
                        origin = getattr(ann, "__args__", None)
                        if origin:
                            inner = next((t for t in origin if t is not type(None)), None)
                            if inner is not None:
                                try:
                                    value = inner(value)
                                except (TypeError, ValueError):
                                    pass
                    setattr(s, key, value)
                elif isinstance(current, bool):
                    setattr(s, key, bool(value))
                else:
                    setattr(s, key, type(current)(value))

    cli = vars(args)
    for key, value in cli.items():
        if key == "config" or value is None:
            continue
        if hasattr(s, key):
            setattr(s, key, value)

    validate_settings(s)
    return s


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.
    
    Returns:
        Parsed arguments namespace.
    """
    p = argparse.ArgumentParser(
        description="Wax and Wane – ambient-light keyboard/screen brightness daemon",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--config", metavar="PATH",
                   help="JSON config file (CLI flags override)")
    p.add_argument("--poll-interval", dest="poll_interval_sec", type=float, default=None,
                   metavar="SEC", help="Seconds between brightness updates")
    p.add_argument("--smoothing-window", dest="smoothing_window", type=int, default=None,
                   metavar="N", help="Number of samples to average")
    p.add_argument("--camera-index", dest="camera_index", type=int, default=None,
                   metavar="N", help="OpenCV camera index")
    p.add_argument("--capture-frames", dest="capture_frames", type=int, default=None,
                   metavar="N", help="Frames to grab per poll")
    p.add_argument("--change-threshold", dest="change_threshold", type=float, default=None,
                   metavar="0-1", help="Minimum brightness delta to trigger update")
    p.add_argument("--rise-threshold", dest="rise_threshold", type=float, default=None,
                   metavar="0-1", help="Brightness increase delta threshold")
    p.add_argument("--fall-threshold", dest="fall_threshold", type=float, default=None,
                   metavar="0-1", help="Brightness decrease delta threshold")
    p.add_argument("--min-update-interval", dest="min_update_interval_sec", type=float, default=None,
                   metavar="SEC", help="Minimum seconds between backend writes")
    p.add_argument("--ambient-dark", dest="ambient_dark", type=float, default=None, metavar="0-1")
    p.add_argument("--ambient-bright", dest="ambient_bright", type=float, default=None, metavar="0-1")
    p.add_argument("--output-gamma", dest="output_gamma", type=float, default=None)
    p.add_argument("--keyboard-min", dest="keyboard_min", type=float, default=None, metavar="0-1")
    p.add_argument("--keyboard-max", dest="keyboard_max", type=float, default=None, metavar="0-1")
    p.add_argument("--keyboard-control", dest="keyboard_control", 
                   choices=("auto", "manual", "system"), default=None,
                   help="Keyboard mode: ambient auto, fixed manual, or leave to system")
    p.add_argument("--manual-keyboard", dest="manual_keyboard_brightness", type=float, default=None,
                   metavar="0-1", help="Fixed keyboard brightness when --keyboard-control=manual")
    p.add_argument("--keyboard-backend", dest="keyboard_backend", default=None,
                   help="Preferred keyboard backend name")
    p.add_argument("--invert-keyboard", dest="invert_keyboard", 
                   type=lambda x: x.lower() != "false", default=None,
                   metavar="true|false", help="Invert keyboard mapping (bright→dark)")
    p.add_argument("--screen-min", dest="screen_min", type=float, default=None, metavar="0-1")
    p.add_argument("--screen-max", dest="screen_max", type=float, default=None, metavar="0-1")
    p.add_argument("--screen-control", dest="screen_control", 
                   choices=("auto", "manual", "system"), default=None,
                   help="Screen mode: ambient auto, fixed manual, or leave to system")
    p.add_argument("--manual-screen", dest="manual_screen_brightness", type=float, default=None,
                   metavar="0-1", help="Fixed screen brightness when --screen-control=manual")
    p.add_argument("--screen-backend", dest="screen_backend", default=None,
                   help="Preferred screen backend name")
    p.add_argument("--invert-screen", dest="invert_screen", 
                   type=lambda x: x.lower() != "false", default=None,
                   metavar="true|false")
    p.add_argument("--default-keyboard", dest="default_keyboard_brightness", 
                   type=float, default=None, metavar="0-1",
                   help="Keyboard brightness restored on exit")
    p.add_argument("--default-screen", dest="default_screen_brightness", 
                   type=float, default=None, metavar="0-1",
                   help="Screen brightness restored on exit")
    p.add_argument("--dry-run", dest="dry_run", action="store_const", const=True, default=None,
                   help="Print backend commands without changing brightness")
    p.add_argument("--restore-original-brightness", dest="restore_original_brightness", 
                   action="store_true", default=None)
    p.add_argument("--no-restore-original-brightness", dest="restore_original_brightness", 
                   action="store_false")
    p.add_argument("--max-runtime", dest="max_runtime_sec", type=float, default=None,
                   metavar="SEC", help="Stop after this many seconds (0=unlimited)")
    p.add_argument("--print-default-config", action="store_true", 
                   help="Print a complete JSON config template and exit")
    p.add_argument("--doctor", action="store_true", 
                   help="Check backends and platform prerequisites, then exit")
    return p.parse_args()
