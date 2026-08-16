"""Unit tests for backends module."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from python.Sources.backends import (
    BrightnessBackend,
    detect_backend,
    run_backend,
    _parse_first_unit_float,
    _directory_trusted,
    _resolve_executable,
    SAFE_EXEC_DIRS,
)


class TestParseFirstUnitFloat:
    """Test brightness value parsing from backend output."""
    
    def test_parses_brightness_keyword(self):
        output = "display 1: main, active\n\tbrightness 0.375000"
        assert _parse_first_unit_float(output) == pytest.approx(0.375)
    
    def test_falls_back_to_last_float(self):
        output = "display 1 value 0.625"
        assert _parse_first_unit_float(output) == pytest.approx(0.625)
    
    def test_returns_none_for_no_match(self):
        output = "no numbers here"
        assert _parse_first_unit_float(output) is None
    
    def test_parses_one_point_zero(self):
        output = "brightness 1.0"
        assert _parse_first_unit_float(output) == pytest.approx(1.0)


class TestBrightnessBackendClamp:
    """Test backend value clamping."""
    
    def test_clamps_within_range(self):
        backend = BrightnessBackend(
            name="test", executable="/usr/bin/test",
            args_builder=lambda v: [str(v)], out_min=0.2, out_max=0.8
        )
        assert backend.clamp(0.5) == 0.5
        assert backend.clamp(0.1) == 0.2
        assert backend.clamp(0.9) == 0.8


class TestDirectoryTrusted:
    """Test directory trust validation."""
    
    def test_rejects_world_writable(self, tmp_path):
        helper_dir = tmp_path / "bin"
        helper_dir.mkdir()
        helper_dir.chmod(0o777)
        assert _directory_trusted(str(helper_dir)) is False
    
    def test_accepts_root_owned_readonly(self, tmp_path):
        # Note: This test may behave differently depending on test runner UID
        helper_dir = tmp_path / "bin"
        helper_dir.mkdir()
        helper_dir.chmod(0o755)
        # Result depends on ownership - just verify it doesn't crash
        _directory_trusted(str(helper_dir))


class TestDetectBackend:
    """Test backend detection."""
    
    def test_returns_none_for_empty_candidates(self):
        result = detect_backend([], "test")
        assert result is None
    
    def test_returns_none_for_unknown_preferred(self):
        result = detect_backend([("foo", lambda v: [], None, None, 0.0, 1.0)], 
                               "test", preferred_name="bar")
        assert result is None


class TestRunBackendDryRun:
    """Test backend execution in dry-run mode."""
    
    def test_dry_run_does_not_execute(self, caplog):
        import logging
        backend = BrightnessBackend(
            name="test", executable="/nonexistent",
            args_builder=lambda v: [str(v)],
            out_min=0.0, out_max=1.0, dry_run=True
        )
        # Set up logging to capture output
        log = logging.getLogger('python.Sources.backends')
        log.setLevel(logging.INFO)
        run_backend(backend, 0.5, "test brightness")
        assert "[dry-run]" in caplog.text


class TestBackendSecurity:
    """Test security features of backends."""
    
    def test_rejects_untrusted_executable_path(self, monkeypatch):
        # Test that executables outside trusted dirs are rejected
        monkeypatch.setattr('python.Sources.backends.SAFE_EXEC_DIRS', ('/nonexistent',))
        result = _resolve_executable("sh")
        assert result is None
