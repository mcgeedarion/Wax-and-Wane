#!/usr/bin/env python3
"""Camera module for Wax and Wane.

Handles webcam capture and ambient light estimation from video frames.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

# Lazy import cv2/numpy to handle missing dependencies gracefully
try:
    import cv2 as _cv2
    import numpy as _np
    _CV2_AVAILABLE = True
except ImportError:  # pragma: no cover
    _cv2 = None  # type: ignore[assignment]
    _np = None  # type: ignore[assignment]
    _CV2_AVAILABLE = False


def is_camera_available() -> bool:
    """Check if OpenCV camera support is available."""
    return _CV2_AVAILABLE


def open_camera(camera_index: int) -> Optional["cv2.VideoCapture"]:
    """Open webcam for ambient light capture.
    
    Args:
        camera_index: OpenCV camera device index.
        
    Returns:
        VideoCapture object or None if camera cannot be opened.
    """
    if not _CV2_AVAILABLE:
        log.error("opencv-python is required for camera access")
        return None
    
    cap = _cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        log.error(
            "Cannot open webcam. Check camera permissions in "
            "System Settings → Privacy & Security → Camera."
        )
        return None
    return cap


def warmup_camera(cap, frames: int = 15, delay: float = 0.2) -> bool:
    """Warm up camera auto-exposure by capturing initial frames.
    
    Args:
        cap: VideoCapture object.
        frames: Number of warmup frames to capture.
        delay: Delay between frames in seconds.
        
    Returns:
        True if warmup completed, False on error.
    """
    if not _CV2_AVAILABLE:
        return False
    
    try:
        for _ in range(frames):
            cap.read()
            import time
            time.sleep(delay)
        return True
    except Exception as exc:
        log.warning("Camera warmup error: %s", exc)
        return False


def capture_mean_brightness(cap, n_frames: int = 3) -> Optional[float]:
    """Calculate average brightness from camera frames.
    
    Captures multiple frames and computes mean luminance from HSV color space.
    No inter-frame sleep - callers should throttle via poll_interval_sec.
    
    Args:
        cap: VideoCapture object (must be opened).
        n_frames: Number of frames to average.
        
    Returns:
        Normalized brightness value [0, 1], or None if no valid frames captured.
    """
    if not _CV2_AVAILABLE or cap is None:
        return None
    
    values = []
    for _ in range(n_frames):
        try:
            ret, frame = cap.read()
        except Exception as exc:
            log.warning("Camera read error: %s", exc)
            continue
            
        if not ret or frame is None:
            continue
            
        try:
            small = _cv2.resize(frame, (64, 48))
            hsv = _cv2.cvtColor(small, _cv2.COLOR_BGR2HSV)
            values.append(float(_np.mean(hsv[:, :, 2]) / 255.0))
        except Exception as exc:
            log.warning("Failed to process camera frame: %s", exc)
            continue
            
    return float(_np.mean(values)) if values else None


def release_camera(cap) -> None:
    """Release camera resources.
    
    Args:
        cap: VideoCapture object to release.
    """
    if cap is not None:
        try:
            cap.release()
        except Exception as exc:
            log.warning("Error releasing camera: %s", exc)
