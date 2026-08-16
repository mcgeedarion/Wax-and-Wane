#!/usr/bin/env python3
"""Backend module for Wax and Wane.

Handles detection and execution of brightness control backends.
Provides security-hardened subprocess execution.
"""

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

log = logging.getLogger(__name__)

# Security: Only allow executables from trusted directories
SAFE_EXEC_DIRS = ("/usr/bin", "/usr/local/bin", "/opt/homebrew/bin")
SAFE_ENV = {"PATH": ":".join(SAFE_EXEC_DIRS), "HOME": os.path.expanduser("~")}
TRUSTED_CWD = os.path.expanduser("~")
BACKEND_TIMEOUT_SEC = 5.0


def _directory_trusted(path: str) -> bool:
    """Check if a directory is safe for child execution.
    
    Validates ownership and permissions to prevent privilege escalation.
    
    Args:
        path: Directory path to validate.
        
    Returns:
        True if directory is trusted, False otherwise.
    """
    try:
        st = os.stat(path)
    except OSError as exc:
        log.warning("Ignoring helper directory %s: %s", path, exc)
        return False

    # Reject group- or world-writable directories
    if st.st_mode & 0o022:
        log.warning("Ignoring writable helper directory: %s", path)
        return False

    effective_uid = os.geteuid() if hasattr(os, "geteuid") else os.getuid()
    trusted_owners = {0} if effective_uid == 0 else {0, effective_uid}
    if st.st_uid not in trusted_owners:
        log.warning("Ignoring helper directory with untrusted owner uid %s: %s", 
                    st.st_uid, path)
        return False
    return True


def _trusted_exec_dirs() -> Tuple[str, ...]:
    """Get list of trusted executable directories."""
    return tuple(path for path in SAFE_EXEC_DIRS if _directory_trusted(path))


def _resolve_executable(name: str) -> Optional[str]:
    """Resolve a helper name to an absolute path under trusted directories.
    
    Validates symlink targets to prevent bypassing the allowlist.
    
    Args:
        name: Executable name to resolve.
        
    Returns:
        Absolute path if found and trusted, None otherwise.
    """
    trusted_dirs = _trusted_exec_dirs()
    if not trusted_dirs:
        log.warning("No trusted helper directories are available.")
        return None
    
    resolved = shutil.which(name, path=":".join(trusted_dirs))
    if not resolved:
        return None
    
    real = os.path.realpath(resolved)
    if any(real.startswith(prefix + os.sep) or real == prefix 
           for prefix in trusted_dirs):
        return real
    
    log.warning("Ignoring unsafe executable path for %s: %s", name, real)
    return None


def _parse_first_unit_float(text: str) -> Optional[float]:
    """Parse first brightness value from backend output.
    
    Args:
        text: Output text from brightness backend.
        
    Returns:
        Parsed float value or None if not found.
    """
    unit_float = r"(?:0(?:\.\d+)?|1(?:\.0+)?)"
    brightness_match = re.search(rf"brightness\s+({unit_float})", text, re.IGNORECASE)
    if brightness_match:
        return float(brightness_match.group(1))

    matches = re.findall(unit_float, text)
    return float(matches[-1]) if matches else None


@dataclass
class BrightnessBackend:
    """Wraps a CLI tool that accepts a normalized [0, 1] brightness value."""
    
    name: str
    executable: str
    args_builder: Callable[[float], List[str]]
    out_min: float
    out_max: float
    read_builder: Optional[Callable[[], List[str]]] = None
    read_parser: Optional[Callable[[str], Optional[float]]] = None
    dry_run: bool = False

    def clamp(self, value: float) -> float:
        """Clamp value to backend's valid range."""
        return float(min(max(value, self.out_min), self.out_max))

    def current_brightness(self) -> Optional[float]:
        """Read current brightness from backend.
        
        Returns:
            Current brightness value or None on error/timeout.
        """
        if not self.read_builder or not self.read_parser:
            return None
        try:
            result = subprocess.run(
                [self.executable] + self.read_builder(),
                check=False,
                capture_output=True,
                text=True,
                cwd=TRUSTED_CWD,
                env=SAFE_ENV,
                timeout=BACKEND_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            log.warning("Timed out reading brightness via %s after %.1fs", 
                       self.name, BACKEND_TIMEOUT_SEC)
            return None
        if result.returncode != 0:
            return None
        return self.read_parser(result.stdout)


# Keyboard backend candidates
_KEYBOARD_CANDIDATES = [
    ("kbrightness", lambda v: [f"{v:.3f}"], None, None, 0.0, 1.0),
    ("mac-brightnessctl", lambda v: [str(int(v * 100))], None, None, 0.0, 1.0),
]

# Screen backend candidates
_SCREEN_CANDIDATES = [
    ("brightness", lambda v: ["-l", f"{v:.3f}"], 
     lambda: ["-l"], _parse_first_unit_float, 0.0, 1.0),
    ("ddcctl", lambda v: ["-b", str(int(v * 100))], None, None, 0.0, 1.0),
]


def detect_backend(
    candidates: list,
    label: str,
    preferred_name: Optional[str] = None,
    dry_run: bool = False,
) -> Optional[BrightnessBackend]:
    """Detect available backend from candidate list.
    
    Args:
        candidates: List of backend tuples (name, builder, reader, parser, min, max).
        label: Human-readable label for logging.
        preferred_name: Optional specific backend to use.
        dry_run: If True, don't actually execute commands.
        
    Returns:
        BrightnessBackend instance or None if no backend found.
    """
    filtered = [c for c in candidates if preferred_name is None or c[0] == preferred_name]
    if not filtered:
        log.warning("Unknown %s backend requested: %s", label, preferred_name)
        return None
    
    for name, builder, reader, parser, out_min, out_max in filtered:
        resolved = _resolve_executable(name)
        if resolved:
            log.info("Using %s backend: %s (%s)", label, name, resolved)
            return BrightnessBackend(
                name=name,
                executable=resolved,
                args_builder=builder,
                read_builder=reader,
                read_parser=parser,
                out_min=out_min,
                out_max=out_max,
                dry_run=dry_run,
            )
    
    log.warning("No %s backend found. %s control disabled.", label, label.capitalize())
    return None


def run_backend(backend: BrightnessBackend, value: float, label: str) -> None:
    """Execute backend command to set brightness.
    
    Args:
        backend: BrightnessBackend instance.
        value: Brightness value [0, 1].
        label: Human-readable label for logging.
    """
    clamped = backend.clamp(value)
    cmd = [backend.executable] + backend.args_builder(clamped)
    
    if backend.dry_run:
        log.info("[dry-run] %s", " ".join(cmd))
        return
    
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            cwd=TRUSTED_CWD,
            env=SAFE_ENV,
            timeout=BACKEND_TIMEOUT_SEC,
        )
        log.debug("Set %s via %s → %.3f", label, backend.name, clamped)
    except subprocess.TimeoutExpired:
        log.warning("Timed out setting %s via %s after %.1fs", 
                   label, backend.name, BACKEND_TIMEOUT_SEC)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="ignore").strip()
        log.warning("Failed to set %s via %s: %s", label, backend.name, stderr)
