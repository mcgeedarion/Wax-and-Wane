"""Integration tests for Wax and Wane Python implementation.

These tests verify the full workflow from configuration to brightness calculation.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from collections import deque
from python.Sources.settings import Settings, validate_settings, build_settings
from python.Sources.policy import (
    normalize_ambient, 
    map_ambient, 
    compute_targets,
    target_for_channel,
    OutputChannelSettings,
)


class TestFullBrightnessPipeline:
    """Test complete brightness calculation pipeline."""
    
    def test_dark_room_produces_dim_output(self):
        """Simulate dark room scenario: low ambient → dim keyboard/screen."""
        settings = Settings(
            ambient_dark=0.0,
            ambient_bright=1.0,
            output_gamma=1.0,
            keyboard_min=0.0,
            keyboard_max=1.0,
            invert_keyboard=False,
            keyboard_control="auto",
            screen_min=0.2,
            screen_max=1.0,
            invert_screen=False,
            screen_control="auto",
            change_threshold=0.0,
        )
        
        history = deque([0.1], maxlen=5)  # Dark ambient reading
        kbd, scr = compute_targets(history, 0.1, -1.0, -1.0, settings)
        
        assert kbd is not None
        assert kbd < 0.3  # Should be dim
        assert scr is not None
        assert scr < 0.4  # Should be at minimum or close
    
    def test_bright_room_produces_bright_output(self):
        """Simulate bright room: high ambient → bright keyboard/screen."""
        settings = Settings(
            ambient_dark=0.0,
            ambient_bright=1.0,
            output_gamma=1.0,
            keyboard_min=0.0,
            keyboard_max=1.0,
            invert_keyboard=False,
            keyboard_control="auto",
            screen_min=0.2,
            screen_max=1.0,
            invert_screen=False,
            screen_control="auto",
            change_threshold=0.0,
        )
        
        history = deque([0.9], maxlen=5)  # Bright ambient reading
        kbd, scr = compute_targets(history, 0.9, -1.0, -1.0, settings)
        
        assert kbd is not None
        assert kbd > 0.7  # Should be bright
        assert scr is not None
        assert scr > 0.8  # Should be near max
    
    def test_inverted_keyboard_mapping(self):
        """Test inverted keyboard: bright room → dim keyboard."""
        settings = Settings(
            ambient_dark=0.0,
            ambient_bright=1.0,
            output_gamma=1.0,
            keyboard_min=0.0,
            keyboard_max=1.0,
            invert_keyboard=True,  # Inverted!
            keyboard_control="auto",
            screen_control="system",
            change_threshold=0.0,
        )
        
        history = deque([0.9], maxlen=5)  # Bright ambient
        kbd, scr = compute_targets(history, 0.9, -1.0, -1.0, settings)
        
        assert kbd is not None
        assert kbd < 0.3  # Bright room should give dim keyboard when inverted
        assert scr is None  # Screen is system-controlled


class TestSmoothingBehavior:
    """Test smoothing window behavior."""
    
    def test_smoothing_damps_single_spike(self):
        """A single outlier should not cause large brightness jump."""
        settings = Settings(
            smoothing_window=5,
            ambient_dark=0.0,
            ambient_bright=1.0,
            keyboard_min=0.0,
            keyboard_max=1.0,
            change_threshold=0.02,
            keyboard_control="auto",
            screen_control="system",
        )
        
        # Build history of stable readings
        history = deque([0.5, 0.5, 0.5, 0.5, 0.5], maxlen=5)
        
        # Single spike to 1.0
        kbd, _ = compute_targets(history, 1.0, 0.5, -1.0, settings)
        
        # Smoothed value should be (0.5*4 + 1.0)/5 = 0.6
        # So keyboard should be around 0.6, not 1.0
        if kbd is not None:
            assert abs(kbd - 0.6) < 0.1


class TestThresholdBehavior:
    """Test change threshold behavior."""
    
    def test_no_change_below_threshold(self):
        """Small changes below threshold should not trigger update."""
        settings = Settings(
            change_threshold=0.1,  # 10% threshold
            keyboard_control="auto",
            screen_control="system",
            keyboard_min=0.0,
            keyboard_max=1.0,
        )
        
        history = deque([0.5], maxlen=5)
        kbd, _ = compute_targets(history, 0.5, 0.5, -1.0, settings)
        
        assert kbd is None  # No change, so no update
    
    def test_change_above_threshold_triggers(self):
        """Large changes above threshold should trigger update."""
        settings = Settings(
            change_threshold=0.05,  # 5% threshold
            keyboard_control="auto",
            screen_control="system",
            keyboard_min=0.0,
            keyboard_max=1.0,
        )
        
        history = deque([0.1], maxlen=5)
        kbd, _ = compute_targets(history, 0.1, 0.9, -1.0, settings)
        
        assert kbd is not None  # Large change triggers update


class TestManualMode:
    """Test manual brightness control mode."""
    
    def test_manual_keyboard_fixed_value(self):
        """Manual mode should use fixed value regardless of ambient."""
        settings = Settings(
            keyboard_control="manual",
            manual_keyboard_brightness=0.42,
            screen_control="system",
            change_threshold=0.0,
        )
        
        history = deque([0.9], maxlen=5)  # Bright ambient
        kbd, _ = compute_targets(history, 0.9, -1.0, -1.0, settings)
        
        assert kbd == pytest.approx(0.42)
    
    def test_system_mode_returns_none(self):
        """System mode should return None (no adjustment)."""
        settings = Settings(
            keyboard_control="system",
            screen_control="system",
        )
        
        history = deque([0.5], maxlen=5)
        kbd, scr = compute_targets(history, 0.5, 0.5, 0.5, settings)
        
        assert kbd is None
        assert scr is None


class TestGammaCorrection:
    """Test gamma correction effects."""
    
    def test_gamma_greater_than_one_darkens_midtones(self):
        """Gamma > 1 should make midtones darker."""
        normalized = normalize_ambient(0.5, 0.0, 1.0, gamma=2.0)
        assert normalized < 0.5  # Gamma 2.0: 0.5^2 = 0.25
    
    def test_gamma_less_than_one_brightens_midtones(self):
        """Gamma < 1 should make midtones brighter."""
        normalized = normalize_ambient(0.5, 0.0, 1.0, gamma=0.5)
        assert normalized > 0.5  # Gamma 0.5: sqrt(0.5) ≈ 0.707


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_history_uses_current(self):
        """Empty history should use current ambient value."""
        settings = Settings(
            keyboard_control="auto",
            screen_control="system",
            keyboard_min=0.0,
            keyboard_max=1.0,
            change_threshold=0.0,
        )
        
        history = deque(maxlen=5)
        kbd, _ = compute_targets(history, 0.7, -1.0, -1.0, settings)
        
        assert kbd == pytest.approx(0.7)
    
    def test_equal_dark_bright_calibration(self):
        """When dark==bright, should return 0.5^gamma."""
        result = normalize_ambient(0.5, 0.5, 0.5, gamma=1.0)
        assert result == pytest.approx(0.5)
    
    def test_clamped_ambient_values(self):
        """Ambient values outside [0,1] should be clamped."""
        # Values are clamped in normalize_ambient
        dark_result = normalize_ambient(-0.5, 0.0, 1.0, gamma=1.0)
        bright_result = normalize_ambient(1.5, 0.0, 1.0, gamma=1.0)
        
        assert dark_result == 0.0
        assert bright_result == 1.0
