"""Unit tests for pure policy functions in python/Sources/main.py.

Run with:  python -m pytest python/Tests
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from collections import deque
import pytest
from python.Sources.main import map_ambient, compute_targets, Settings


# BUG-05 fix: pytest collects classes whose names start with "Test".
# All classes renamed from *Tests -> Test* to follow pytest conventions.

class TestMapAmbient:
    def test_no_invert_min(self):
        assert map_ambient(0.0, 0.2, 1.0, invert=False) == pytest.approx(0.2)

    def test_no_invert_max(self):
        assert map_ambient(1.0, 0.2, 1.0, invert=False) == pytest.approx(1.0)

    def test_no_invert_mid(self):
        assert map_ambient(0.5, 0.0, 1.0, invert=False) == pytest.approx(0.5)

    def test_invert_min(self):
        assert map_ambient(0.0, 0.0, 1.0, invert=True) == pytest.approx(1.0)

    def test_invert_max(self):
        assert map_ambient(1.0, 0.0, 1.0, invert=True) == pytest.approx(0.0)

    def test_invert_mid(self):
        assert map_ambient(0.5, 0.0, 1.0, invert=True) == pytest.approx(0.5)

    def test_clamping_not_done_here(self):
        result = map_ambient(2.0, 0.0, 1.0, invert=False)
        assert result == pytest.approx(2.0)



def _default_settings(**overrides) -> Settings:
    s = Settings()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# BUG-02 fix applied to tests: history.append() is now the caller's responsibility.
# Each helper that was previously relying on compute_targets to append must append
# explicitly before calling compute_targets.
class TestComputeTargets:
    def _history(self, window: int = 5) -> deque:
        return deque(maxlen=window)

    def test_first_sample_always_triggers(self):
        h = self._history()
        s = _default_settings(change_threshold=0.02)
        h.append(0.5)
        kbd, scr = compute_targets(h, 0.5, last_keyboard=-1.0, last_screen=-1.0, s=s)
        assert kbd is not None
        assert scr is not None

    def test_no_change_below_threshold(self):
        h = self._history()
        s = _default_settings(change_threshold=0.05)
        h.append(0.5)
        compute_targets(h, 0.5, -1.0, -1.0, s)
        h.append(0.5)
        kbd, scr = compute_targets(h, 0.5, 0.5, 0.3, s)
        assert kbd is None

    def test_change_above_threshold_triggers(self):
        h = self._history()
        s = _default_settings(change_threshold=0.02)
        h.append(0.1)
        compute_targets(h, 0.1, -1.0, -1.0, s)
        h.append(0.9)
        kbd, scr = compute_targets(h, 0.9, 0.1, 0.1, s)
        assert kbd is not None
        assert scr is not None

    def test_smoothing_damps_spike(self):
        """A single outlier frame should not immediately drive a large jump
        when the smoothing window is large."""
        h = self._history(window=5)
        s = _default_settings(change_threshold=0.02,
                               smoothing_window=5,
                               keyboard_min=0.0, keyboard_max=1.0,
                               invert_keyboard=False)
        for _ in range(5):
            h.append(0.5)
            compute_targets(h, 0.5, -1.0, -1.0, s)
        h.append(1.0)
        kbd, _ = compute_targets(h, 1.0, 0.5, 0.5, s)
        if kbd is not None:
            assert abs(kbd - 0.5) < 0.2

    def test_history_appended(self):
        h = self._history(window=3)
        s = _default_settings()
        h.append(0.3)
        compute_targets(h, 0.3, -1.0, -1.0, s)
        h.append(0.6)
        compute_targets(h, 0.6, 0.0, 0.0, s)
        assert len(h) == 2

    def test_keyboard_dark_room_dim(self):
        """With invert_keyboard=False (default), dark ambient (0.0) -> keyboard_min."""
        h = self._history()
        s = _default_settings(invert_keyboard=False,
                               keyboard_min=0.0, keyboard_max=1.0,
                               change_threshold=0.0)
        h.append(0.0)
        kbd, _ = compute_targets(h, 0.0, -1.0, -1.0, s)
        assert kbd == pytest.approx(0.0)

    def test_keyboard_bright_room_bright(self):
        """With invert_keyboard=False (default), bright ambient (1.0) -> keyboard_max."""
        h = self._history()
        s = _default_settings(invert_keyboard=False,
                               keyboard_min=0.0, keyboard_max=1.0,
                               change_threshold=0.0)
        h.append(1.0)
        kbd, _ = compute_targets(h, 1.0, -1.0, -1.0, s)
        assert kbd == pytest.approx(1.0)

    def test_screen_no_invert(self):
        """With invert_screen=False, bright ambient (1.0) -> max screen."""
        h = self._history()
        s = _default_settings(invert_screen=False,
                               screen_min=0.2, screen_max=1.0,
                               change_threshold=0.0)
        h.append(1.0)
        _, scr = compute_targets(h, 1.0, -1.0, -1.0, s)
        assert scr == pytest.approx(1.0)

    def test_manual_keyboard_does_not_affect_screen(self):
        h = self._history()
        s = _default_settings(keyboard_control="manual",
                               manual_keyboard_brightness=0.25,
                               screen_control="system",
                               change_threshold=0.0)
        h.append(1.0)
        kbd, scr = compute_targets(h, 1.0, -1.0, -1.0, s)
        assert kbd == pytest.approx(0.25)
        assert scr is None

    def test_manual_screen_does_not_affect_keyboard(self):
        h = self._history()
        s = _default_settings(keyboard_control="system",
                               screen_control="manual",
                               manual_screen_brightness=0.8,
                               change_threshold=0.0)
        h.append(0.0)
        kbd, scr = compute_targets(h, 0.0, -1.0, -1.0, s)
        assert kbd is None
        assert scr == pytest.approx(0.8)


class TestSettingsValidation:
    def test_rejects_zero_smoothing_window(self):
        from python.Sources.main import validate_settings
        s = _default_settings(smoothing_window=0)
        with pytest.raises(ValueError, match="smoothing_window"):
            validate_settings(s)

    def test_rejects_invalid_brightness_range(self):
        from python.Sources.main import validate_settings
        s = _default_settings(screen_min=0.9, screen_max=0.2)
        with pytest.raises(ValueError, match="screen_min"):
            validate_settings(s)

    def test_calibration_gamma_changes_auto_target(self):
        h = deque(maxlen=1)
        s = _default_settings(ambient_dark=0.2, ambient_bright=0.8, output_gamma=2.0,
                              keyboard_min=0.0, keyboard_max=1.0, change_threshold=0.0)
        h.append(0.5)
        kbd, _ = compute_targets(h, 0.5, -1.0, -1.0, s)
        assert kbd == pytest.approx(0.25)

    # BUG-13 fix: validate that output_gamma rejects values > 10.
    def test_rejects_output_gamma_above_upper_bound(self):
        from python.Sources.main import validate_settings
        s = _default_settings(output_gamma=11.0)
        with pytest.raises(ValueError, match="output_gamma"):
            validate_settings(s)


class TestBrightnessParser:
    def test_prefers_brightness_value_over_display_id(self):
        from python.Sources.main import _parse_first_unit_float

        output = "display 1: main, active\n\tbrightness 0.375000"

        assert _parse_first_unit_float(output) == pytest.approx(0.375)

    def test_falls_back_to_last_unit_float(self):
        from python.Sources.main import _parse_first_unit_float

        assert _parse_first_unit_float("display 1 value 0.625") == pytest.approx(0.625)


class TestCapture:
    def test_capture_mean_brightness_returns_none_when_no_frames(self, monkeypatch):
        import sys
        import types
        import python.Sources.main as main

        class FakeCap:
            def read(self):
                return False, None

        fake_cv2 = types.SimpleNamespace()
        fake_np = types.SimpleNamespace(mean=lambda x: 0.0)
        # BUG-07 fix: monkeypatch the module-level _cv2/_np instead of sys.modules.
        monkeypatch.setattr(main, "_cv2", fake_cv2)
        monkeypatch.setattr(main, "_np", fake_np)

        assert main.capture_mean_brightness(FakeCap(), n_frames=3) is None


class TestBackendSecurity:
    def test_backend_read_timeout_returns_none(self, monkeypatch):
        import sys
        import python.Sources.main as main

        monkeypatch.setattr(main, "BACKEND_TIMEOUT_SEC", 0.1)
        backend = main.BrightnessBackend(
            name="slow-read",
            executable=sys.executable,
            args_builder=lambda _: [],
            out_min=0.0,
            out_max=1.0,
            read_builder=lambda: ["-c", "import time; time.sleep(2)"],
            read_parser=lambda _: 0.5,
        )

        assert backend.current_brightness() is None

    def test_backend_write_timeout_does_not_raise(self, monkeypatch):
        import sys
        import python.Sources.main as main

        monkeypatch.setattr(main, "BACKEND_TIMEOUT_SEC", 0.1)
        backend = main.BrightnessBackend(
            name="slow-write",
            executable=sys.executable,
            args_builder=lambda _: ["-c", "import time; time.sleep(2)"],
            out_min=0.0,
            out_max=1.0,
        )

        main.run_backend(backend, 0.5, "test brightness")

    def test_rejects_world_writable_helper_directory(self, tmp_path, monkeypatch):
        import python.Sources.main as main

        helper_dir = tmp_path / "bin"
        helper_dir.mkdir()
        helper = helper_dir / "brightness"
        helper.write_text("#!/bin/sh\nexit 0\n")
        helper.chmod(0o755)
        helper_dir.chmod(0o777)
        monkeypatch.setattr(main, "SAFE_EXEC_DIRS", (str(helper_dir),))

        try:
            assert main._resolve_executable("brightness") is None
        finally:
            helper_dir.chmod(0o755)
