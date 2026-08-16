#!/usr/bin/env python3
"""CLI module for Wax and Wane.

Provides command-line interface and main entry point.
"""

import argparse
import logging
import sys
import time
from typing import Optional

from .settings import (
    Settings,
    build_settings,
    parse_args,
    default_config_json,
)
from .policy import compute_targets
from .backends import (
    detect_backend,
    run_backend,
    _KEYBOARD_CANDIDATES,
    _SCREEN_CANDIDATES,
)
from .camera import (
    is_camera_available,
    open_camera,
    warmup_camera,
    capture_mean_brightness,
    release_camera,
)

log = logging.getLogger(__name__)


class RuntimeGuard:
    """Manages runtime limits and periodic reminders."""

    def __init__(self, settings: Settings) -> None:
        self._max_runtime = settings.max_runtime_sec
        self._remind_interval = settings.reminder_interval_sec
        self._start = time.monotonic()
        self._last_reminder = self._start

    def should_exit(self) -> bool:
        """Check if maximum runtime has been exceeded."""
        return self._max_runtime > 0 and (time.monotonic() - self._start) >= self._max_runtime

    def maybe_remind(self) -> None:
        """Log reminder about camera usage if interval elapsed."""
        if self._remind_interval <= 0:
            return
        now = time.monotonic()
        if now - self._last_reminder >= self._remind_interval:
            log.info(
                "[Reminder] Wax and Wane is using the camera. "
                "Press Ctrl+C to stop."
            )
            self._last_reminder = now


def doctor() -> None:
    """Run diagnostics on backends and dependencies."""
    from .backends import SAFE_EXEC_DIRS, _resolve_executable
    
    log.info("Wax and Wane doctor")
    log.info("Safe executable directories: %s", ", ".join(SAFE_EXEC_DIRS))
    
    for label, candidates in (("keyboard", _KEYBOARD_CANDIDATES), 
                               ("screen", _SCREEN_CANDIDATES)):
        log.info("%s backends:", label.capitalize())
        for name, *_ in candidates:
            resolved = _resolve_executable(name)
            status = "✓" if resolved else "✗"
            log.info("  %s %s: %s", status, name, resolved or "not found")
    
    import importlib.util
    cv2_status = "available" if importlib.util.find_spec("cv2") else "unavailable"
    log.info("OpenCV import: %s", cv2_status)


def run_main_loop(settings: Optional[Settings] = None) -> None:
    """Main brightness control loop.
    
    Args:
        settings: Settings object. If None, will parse from CLI args.
    """
    if not is_camera_available():
        log.error("opencv-python is required. Install with: pip install opencv-python numpy")
        sys.exit(1)
    
    if settings is None:
        args = parse_args()
        if getattr(args, "print_default_config", False):
            print(default_config_json())
            return
        if getattr(args, "doctor", False):
            doctor()
            return
        settings = build_settings(args)
    
    # Validate settings
    from .settings import validate_settings
    validate_settings(settings)
    
    keyboard_enabled = settings.keyboard_control != "system"
    screen_enabled = settings.screen_control != "system"
    
    keyboard_backend = (
        detect_backend(_KEYBOARD_CANDIDATES, "keyboard", 
                      settings.keyboard_backend, settings.dry_run) 
        if keyboard_enabled else None
    )
    screen_backend = (
        detect_backend(_SCREEN_CANDIDATES, "screen", 
                      settings.screen_backend, settings.dry_run) 
        if screen_enabled else None
    )

    if not keyboard_enabled and not screen_enabled:
        log.error("Keyboard and screen are both set to system control; nothing to adjust.")
        sys.exit(1)

    if (keyboard_enabled and keyboard_backend is None) and \
       (screen_enabled and screen_backend is None):
        log.error("No enabled output backends available. "
                  "Install a backend or set that channel to system control.")
        sys.exit(1)

    cap = open_camera(settings.camera_index)
    if cap is None:
        sys.exit(1)

    log.info("Camera active. Warming up auto-exposure (3 s)…")
    try:
        if not warmup_camera(cap):
            log.error("Camera warmup failed")
            release_camera(cap)
            return
    except KeyboardInterrupt:
        log.info("Interrupted during warmup. Restoring defaults.")
        release_camera(cap)
        return

    # Get original brightness for restoration
    original_keyboard = (
        keyboard_backend.current_brightness() 
        if keyboard_backend and settings.restore_original_brightness 
        else None
    )
    original_screen = (
        screen_backend.current_brightness() 
        if screen_backend and settings.restore_original_brightness 
        else None
    )

    history: "deque[float]" = __import__("collections").deque(
        maxlen=settings.smoothing_window
    )
    last_keyboard = original_keyboard if original_keyboard is not None else -1.0
    last_screen = original_screen if original_screen is not None else -1.0
    last_write_keyboard = 0.0
    last_write_screen = 0.0
    guard = RuntimeGuard(settings)

    def restore_defaults(
        _kbd=original_keyboard,
        _scr=original_screen,
    ) -> None:
        """Restore brightness to original or default values."""
        if keyboard_backend and settings.keyboard_control != "system":
            run_backend(
                keyboard_backend, 
                _kbd if _kbd is not None else settings.default_keyboard_brightness, 
                "keyboard brightness"
            )
        if screen_backend and settings.screen_control != "system":
            run_backend(
                screen_backend, 
                _scr if _scr is not None else settings.default_screen_brightness, 
                "screen brightness"
            )

    log.info("Ambient loop started. Ctrl+C to stop.")
    try:
        while True:
            if guard.should_exit():
                log.info("Max runtime reached. Stopping.")
                break
            guard.maybe_remind()

            ambient = capture_mean_brightness(cap, settings.capture_frames)
            if ambient is None:
                log.warning("No valid camera frames captured; skipping this poll.")
                time.sleep(settings.poll_interval_sec)
                continue

            history.append(ambient)
            new_kbd, new_scr = compute_targets(
                history, ambient, last_keyboard, last_screen, settings
            )

            now = time.monotonic()
            
            if new_kbd is not None and keyboard_backend:
                if (now - last_write_keyboard) >= settings.min_update_interval_sec:
                    run_backend(keyboard_backend, new_kbd, "keyboard brightness")
                    last_keyboard = new_kbd
                    last_write_keyboard = time.monotonic()

            if new_scr is not None and screen_backend:
                if (now - last_write_screen) >= settings.min_update_interval_sec:
                    run_backend(screen_backend, new_scr, "screen brightness")
                    last_screen = new_scr
                    last_write_screen = time.monotonic()

            smoothed = sum(history) / len(history) if history else ambient
            from .policy import normalize_ambient
            calibrated = normalize_ambient(
                smoothed, 
                settings.ambient_dark, 
                settings.ambient_bright, 
                settings.output_gamma
            )
            log.info(
                "Ambient: %.3f (calibrated %.3f) → Keyboard: %s | Screen: %s",
                smoothed,
                calibrated,
                "system" if settings.keyboard_control == "system" else f"{last_keyboard:.3f}",
                "system" if settings.screen_control == "system" else f"{last_screen:.3f}",
            )

            time.sleep(settings.poll_interval_sec)

    except KeyboardInterrupt:
        log.info("Interrupted. Restoring defaults.")
    finally:
        restore_defaults()
        release_camera(cap)


# Compatibility alias
run = run_main_loop


if __name__ == "__main__":
    run_main_loop()
