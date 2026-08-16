#!/usr/bin/env python3
"""Policy module for Wax and Wane.

Contains pure functions for brightness calculation and mapping logic.
No I/O operations - suitable for unit testing.
"""

from typing import Optional, Tuple
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class OutputChannelSettings:
    """Settings needed to compute one brightness channel target."""
    control: str
    minimum: float
    maximum: float
    invert: bool
    manual_value: float


def normalize_ambient(ambient: float, dark: float, bright: float, gamma: float) -> float:
    """Normalize ambient light value to [0, 1] range with gamma correction.
    
    Args:
        ambient: Raw ambient light measurement.
        dark: Calibration point for minimum ambient light.
        bright: Calibration point for maximum ambient light.
        gamma: Gamma correction factor (must be > 0 and <= 10).
        
    Returns:
        Normalized value in [0, 1] range with gamma applied.
    """
    if bright == dark:
        return 0.5 ** gamma
    linear = min(max((ambient - dark) / (bright - dark), 0.0), 1.0)
    return linear ** gamma


def map_ambient(ambient: float, out_min: float, out_max: float, invert: bool) -> float:
    """Map normalized ambient value to output range.
    
    Args:
        ambient: Normalized ambient light value [0, 1].
        out_min: Minimum output value.
        out_max: Maximum output value.
        invert: If True, invert the mapping (bright→dark).
        
    Returns:
        Mapped output value.
    """
    if invert:
        return out_max - ambient * (out_max - out_min)
    return out_min + ambient * (out_max - out_min)


def _threshold_for_delta(delta: float, change_threshold: float, 
                         rise_threshold: Optional[float], 
                         fall_threshold: Optional[float]) -> float:
    """Determine appropriate threshold based on delta direction.
    
    Args:
        delta: Change in brightness value.
        change_threshold: Default threshold for both directions.
        rise_threshold: Optional separate threshold for increases.
        fall_threshold: Optional separate threshold for decreases.
        
    Returns:
        Appropriate threshold value.
    """
    if delta > 0:
        return change_threshold if rise_threshold is None else rise_threshold
    if delta < 0:
        return change_threshold if fall_threshold is None else fall_threshold
    return change_threshold


def target_for_channel(
    channel: OutputChannelSettings,
    smoothed_ambient: float,
    last_value: float,
    change_threshold: float,
    rise_threshold: Optional[float] = None,
    fall_threshold: Optional[float] = None,
) -> Optional[float]:
    """Calculate target brightness for one output channel.
    
    Args:
        channel: Channel configuration settings.
        smoothed_ambient: Smoothed and calibrated ambient light value.
        last_value: Previous brightness setting for this channel.
        change_threshold: Minimum change to trigger update.
        rise_threshold: Optional separate threshold for brightness increases.
        fall_threshold: Optional separate threshold for brightness decreases.
        
    Returns:
        Target brightness value, or None if no change needed or channel is system-controlled.
    """
    if channel.control == "system":
        return None
    if channel.control == "manual":
        target = channel.manual_value
    elif channel.control == "auto":
        target = map_ambient(smoothed_ambient, channel.minimum, channel.maximum, channel.invert)
    else:
        raise ValueError(f"Unsupported brightness control mode: {channel.control}")

    delta = target - last_value
    threshold = _threshold_for_delta(delta, change_threshold, rise_threshold, fall_threshold)
    return target if abs(delta) > threshold else None


def target_for_control(
    control: str,
    smoothed_ambient: float,
    last_value: float,
    minimum: float,
    maximum: float,
    invert: bool,
    manual_value: float,
    change_threshold: float,
    rise_threshold: Optional[float] = None,
    fall_threshold: Optional[float] = None,
) -> Optional[float]:
    """Legacy wrapper for target_for_channel.
    
    Args:
        control: Control mode ("auto", "manual", "system").
        smoothed_ambient: Smoothed ambient light value.
        last_value: Previous brightness value.
        minimum: Minimum output brightness.
        maximum: Maximum output brightness.
        invert: Whether to invert the mapping.
        manual_value: Fixed brightness for manual mode.
        change_threshold: Minimum change threshold.
        rise_threshold: Optional rise-specific threshold.
        fall_threshold: Optional fall-specific threshold.
        
    Returns:
        Target brightness or None.
    """
    return target_for_channel(
        OutputChannelSettings(control, minimum, maximum, invert, manual_value),
        smoothed_ambient,
        last_value,
        change_threshold,
        rise_threshold,
        fall_threshold,
    )


def compute_targets(
    history: deque,
    ambient_now: float,
    last_keyboard: float,
    last_screen: float,
    settings,
) -> Tuple[Optional[float], Optional[float]]:
    """Compute target brightness values for keyboard and screen.
    
    This is a pure function - it performs no I/O and does not mutate history.
    The caller must append ambient_now to history before calling this function.
    
    Args:
        history: Deque of recent ambient light measurements.
        ambient_now: Current ambient light measurement.
        last_keyboard: Previous keyboard brightness value.
        last_screen: Previous screen brightness value.
        settings: Settings object with configuration.
        
    Returns:
        Tuple of (keyboard_target, screen_target), each may be None.
    """
    smoothed = sum(history) / len(history) if history else ambient_now
    calibrated = normalize_ambient(
        smoothed, 
        settings.ambient_dark, 
        settings.ambient_bright, 
        settings.output_gamma
    )

    channels = (
        OutputChannelSettings(
            settings.keyboard_control, 
            settings.keyboard_min, 
            settings.keyboard_max,
            settings.invert_keyboard, 
            settings.manual_keyboard_brightness,
        ),
        OutputChannelSettings(
            settings.screen_control, 
            settings.screen_min, 
            settings.screen_max,
            settings.invert_screen, 
            settings.manual_screen_brightness,
        ),
    )
    return tuple(
        target_for_channel(
            channel, 
            calibrated, 
            last_value, 
            settings.change_threshold,
            settings.rise_threshold, 
            settings.fall_threshold,
        )
        for channel, last_value in zip(channels, (last_keyboard, last_screen))
    )
