# Changelog

All notable changes to Wax and Wane will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Removed the unsupported SwiftPM processing of the camera usage `Info.plist`, and embedded the usage description in the executable.
- Report brightness backend write failures to the control loop so failed writes can be retried.
- Exclude image row padding from ambient luma averages and avoid per-frame float-buffer allocations.
- Restore brightness on SIGTERM as well as SIGINT, with idempotent cleanup.
- Reject non-finite settings and ambiguous unlabeled brightness parser output.
- Bound subprocess output-pipe waits and drain stdout/stderr concurrently.
- Merge partial JSON config files over built-in defaults.
- Add explicit negative inversion flags for CLI overrides.
- Generate LaunchAgent plist files with a plist-aware serializer and remove unsupported pseudo-sandbox keys.
- Update security documentation to reflect the Swift implementation.

### Testing
- Added regression coverage for partial configs, non-finite settings, negative inversion flags, and ambiguous brightness output.

### Added
- Modular Python package structure with separate modules for settings, policy, backends, camera, and CLI
- Unit tests for settings module (`SettingsTests.py`)
- Unit tests for backends module (`BackendTests.py`)
- Integration tests for full workflow verification (`IntegrationTests.py`)
- CONTRIBUTING.md with development guidelines
- CHANGELOG.md for tracking changes
- Version tracking in Python package (`__version__`)

### Changed
- Refactored monolithic `main.py` into modular components
- Improved test coverage for Python implementation
- Updated pytest configuration to support both old and new test class naming conventions

### Security
- Enhanced LaunchAgent security hardening (see SECURITY_AUDIT.md)
- Stricter executable path validation in backends

## [1.0.0] - 2025-01-15

### Added
- Initial release of Wax and Wane
- Native Swift implementation for macOS
- Reference Python implementation
- Automatic keyboard brightness control based on ambient light
- Automatic screen brightness control based on ambient light
- Configurable smoothing window and change thresholds
- Gamma correction for non-linear brightness mapping
- Manual and system control modes
- Dry-run mode for testing
- JSON configuration file support
- CLI argument overrides
- Runtime reminders for camera usage
- Optional max runtime limit
- Brightness restoration on exit
- Backend detection for multiple hardware tools
- Security-hardened subprocess execution
- LaunchAgent support for background operation
- Comprehensive documentation (README.md, SECURITY_AUDIT.md)
- CI/CD pipeline with GitHub Actions
- Example configurations

### Fixed
- Per-channel rate limiting to prevent keyboard/screen write conflicts
- ZeroDivisionError when dark==bright calibration values
- Camera warmup interrupt handling
- Late-binding bugs in restore defaults function
- OpenCV/numpy import optimization for hot paths
- Output gamma validation upper bound

[Unreleased]: https://github.com/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/releases/tag/v1.0.0
