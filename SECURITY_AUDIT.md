# Security Review: Wax and Wane

Date: 2026-10-18

## Scope
- `swift/Sources/WaxAndWaneCore/Backends.swift`
- `swift/Sources/WaxAndWaneCore/MacApp.swift`
- `swift/Sources/WaxAndWaneCore/Settings.swift`
- `swift/Sources/WaxAndWaneCore/CLI.swift`

## Findings

### 1) Backend helper process hang can block the daemon (Medium) — Fixed
The Swift implementation launches local helper tools (`kbrightness`,
`mac-brightnessctl`, `brightness`, `ddcctl`) to read or write brightness. A
malfunctioning, compromised, or unexpectedly interactive helper could run
indefinitely. Because backend calls were synchronous and had no timeout, this
could stop camera-loop progress, prevent later brightness corrections, and delay
shutdown/restore behavior.

Mitigation implemented:
- - Swift backend process execution now enforces the same bounded timeout,
  terminates slow helpers, escalates to `SIGKILL` if needed, and reports timeout
  status to callers.
- Regression tests cover slow-helper timeout behavior in both implementations.

### 2) PATH hijacking of privileged helper binaries (Previously High) — Mitigated
The implementation previously depended on ambient PATH lookup for helper
binaries. That can become arbitrary code execution if the program is run from a
LaunchAgent/daemon or privileged shell with attacker-influenced PATH.

Current mitigation:
- Helper names are selected from fixed candidate lists.
- Executables are resolved only from allow-listed directories:
  `/usr/bin`, `/usr/local/bin`, `/opt/homebrew/bin`.
- Symlink targets are resolved and must also remain under those directories.
- Backend invocations use the resolved absolute executable path.

Residual risk:
- The trusted directories themselves must retain normal system permissions.
  A user-writable directory in this allow-list would reintroduce the risk.

### 3) Untrusted child-process execution context (Previously Medium) — Mitigated
Backend helpers are launched from a trusted working directory and receive a
minimal environment. This avoids inheriting arbitrary current-directory context
and strips high-risk ambient variables such as dynamic-loader and language-path
settings.

### 4) Camera privacy exposure through continuous background capture (Low) — Mitigated
The app continuously samples the camera by design, which is privacy-sensitive
even though frames are only reduced to brightness estimates.

Current mitigation:
- Runtime logs indicate when the camera is active.
- A configurable maximum runtime stops the loop by default.
- Periodic reminders notify/log that camera capture is active.

### 5) Writable trusted helper directories can reintroduce PATH hijacking (Medium) — Fixed
The helper allow-list includes common Homebrew locations. If one of those
locations is group/world writable, or if the daemon is launched with elevated
privileges while a helper directory is owned by an unprivileged account, helper
resolution can again become arbitrary code execution.

Mitigation implemented:
- Swift filters the helper directory allow-list before lookup.
- Helper directories must not be group- or world-writable.
- When running elevated, helper directories must be root-owned; otherwise they
  must be owned by root or the current user.
- The sanitized child-process PATH is built from the same trusted directory set.

## Notes
- No command-injection sink was found: helper commands are executed as argument
  arrays, not through a shell.
- No network-facing surface was identified in this codebase.
- Config files are parsed as JSON into typed settings and validated before use.


## Follow-up audit (2026-10-18)

The Swift implementation is the supported implementation. Historical Python test and module references have been removed from the current scope.

- SwiftPM no longer processes `Info.plist` as a resource. The executable linker embeds the camera usage description in the Mach-O `__info_plist` section.
- Brightness writes return success/failure so control state advances only after successful writes.
- Camera luma calculation uses actual plane width and row stride, excluding row padding and avoiding per-frame float-buffer allocation.
- Settings validation rejects non-finite numeric values, and partial JSON configuration objects inherit built-in defaults.
- Backend output parsing rejects unlabeled ambiguous numeric output.
- Process stdout and stderr are drained concurrently, and waiting for inherited pipe descriptors is bounded.
- SIGINT and SIGTERM use the same idempotent restore path.
- The LaunchAgent no longer contains unsupported pseudo-sandbox/hardened-runtime keys. Those protections require a properly signed application and valid entitlements, not arbitrary launchd plist keys.

Residual verification required: run `swift test` and `swift build -c release` on macOS, test camera permissions and actual hardware backends, and inspect the built executable's `__info_plist` section. Process group termination and strict output-size limits remain candidates for further hardening.
