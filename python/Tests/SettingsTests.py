"""Unit tests for settings module."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from python.Sources.settings import (
    Settings,
    validate_settings,
    load_config,
    build_settings,
    default_config_json,
    parse_args,
)
import json
import tempfile


class TestSettingsDefaults:
    """Test default settings values."""
    
    def test_default_poll_interval(self):
        s = Settings()
        assert s.poll_interval_sec == 2.0
    
    def test_default_smoothing_window(self):
        s = Settings()
        assert s.smoothing_window == 5
    
    def test_default_camera_index(self):
        s = Settings()
        assert s.camera_index == 0
    
    def test_default_brightness_ranges(self):
        s = Settings()
        assert s.keyboard_min == 0.0
        assert s.keyboard_max == 1.0
        assert s.screen_min == 0.2
        assert s.screen_max == 1.0
    
    def test_default_control_modes(self):
        s = Settings()
        assert s.keyboard_control == "auto"
        assert s.screen_control == "auto"


class TestSettingsValidation:
    """Test settings validation."""
    
    def test_valid_settings(self):
        s = Settings()
        validate_settings(s)  # Should not raise
    
    def test_rejects_zero_smoothing_window(self):
        s = Settings(smoothing_window=0)
        with pytest.raises(ValueError, match="smoothing_window"):
            validate_settings(s)
    
    def test_rejects_negative_poll_interval(self):
        s = Settings(poll_interval_sec=-1.0)
        with pytest.raises(ValueError, match="poll_interval_sec"):
            validate_settings(s)
    
    def test_rejects_invalid_brightness_range(self):
        s = Settings(screen_min=0.9, screen_max=0.2)
        with pytest.raises(ValueError, match="screen_min"):
            validate_settings(s)
    
    def test_rejects_ambient_bright_not_greater(self):
        s = Settings(ambient_dark=0.8, ambient_bright=0.2)
        with pytest.raises(ValueError, match="ambient_bright"):
            validate_settings(s)
    
    def test_rejects_output_gamma_zero(self):
        s = Settings(output_gamma=0.0)
        with pytest.raises(ValueError, match="output_gamma"):
            validate_settings(s)
    
    def test_rejects_output_gamma_above_ten(self):
        s = Settings(output_gamma=11.0)
        with pytest.raises(ValueError, match="output_gamma"):
            validate_settings(s)
    
    def test_rejects_invalid_keyboard_control(self):
        s = Settings()
        s.keyboard_control = "invalid"
        with pytest.raises(ValueError, match="keyboard_control"):
            validate_settings(s)
    
    def test_accepts_optional_thresholds_none(self):
        s = Settings(rise_threshold=None, fall_threshold=None)
        validate_settings(s)  # Should not raise
    
    def test_rejects_negative_rise_threshold(self):
        s = Settings(rise_threshold=-0.1)
        with pytest.raises(ValueError, match="rise_threshold"):
            validate_settings(s)


class TestLoadConfig:
    """Test config file loading."""
    
    def test_load_valid_config(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"poll_interval_sec": 5.0}, f)
            f.flush()
            try:
                cfg = load_config(f.name)
                assert cfg["poll_interval_sec"] == 5.0
            finally:
                os.unlink(f.name)
    
    def test_load_invalid_json_object(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("[1, 2, 3]")
            f.flush()
            try:
                with pytest.raises(ValueError, match="JSON object"):
                    load_config(f.name)
            finally:
                os.unlink(f.name)
    
    def test_load_with_unknown_keys(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"unknown_key": "value", "poll_interval_sec": 3.0}, f)
            f.flush()
            try:
                cfg = load_config(f.name)
                assert cfg["poll_interval_sec"] == 3.0
                # Note: unknown keys are logged but still returned in dict
                assert "unknown_key" in cfg
            finally:
                os.unlink(f.name)


class TestDefaultConfigJson:
    """Test default config JSON generation."""
    
    def test_returns_valid_json(self):
        result = default_config_json()
        data = json.loads(result)
        assert isinstance(data, dict)
        assert "poll_interval_sec" in data
    
    def test_all_settings_present(self):
        result = default_config_json()
        data = json.loads(result)
        expected_keys = set(Settings().__dict__.keys())
        assert set(data.keys()) == expected_keys


class TestBuildSettings:
    """Test settings building from args and config."""
    
    def test_cli_overrides_config(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"poll_interval_sec": 10.0}, f)
            f.flush()
            try:
                class Args:
                    config = f.name
                    poll_interval_sec = None  # Use config value
                    smoothing_window = None  # Use default
                args = Args()
                s = build_settings(args)
                assert s.poll_interval_sec == 10.0  # From config
                assert s.smoothing_window == 5  # Default
            finally:
                os.unlink(f.name)
    
    def test_config_overrides_defaults(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"poll_interval_sec": 7.0}, f)
            f.flush()
            try:
                class Args:
                    config = f.name
                    poll_interval_sec = None
                args = Args()
                s = build_settings(args)
                assert s.poll_interval_sec == 7.0
            finally:
                os.unlink(f.name)
    
    def test_no_config_uses_defaults(self):
        class Args:
            config = None
            poll_interval_sec = None
        args = Args()
        s = build_settings(args)
        assert s.poll_interval_sec == 2.0  # Default
