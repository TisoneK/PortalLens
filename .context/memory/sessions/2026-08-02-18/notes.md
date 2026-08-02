# Session 18 notes — deterministic desktop Wi-Fi adapters

## Goal

Continue Session 17 with a hardware-independent desktop adapter slice. Keep the
implementation read-only: discover visible networks and report host status,
without credentials, association, packet operations, browser launch, or bypass
execution.

## Shipped

- Added `portallens.wifi.command` with injectable `CommandRunner`, typed command
  result, shell-free subprocess execution, bounded timeout, UTF-8 replacement
  decoding, typed unavailable/permission/timeout errors, and interruptible
  cancellation using `Popen` polling.
- Added `portallens.wifi.adapters` with Windows `netsh`, macOS `airport` and
  `networksetup`, and Linux NetworkManager `nmcli` adapters.
- Added parsers for scan/status output, signal/security normalization, hidden
  SSID handling, BSSID normalization through the domain model, and scan
  deduplication.
- Adapters advertise scan/status only. Connect/disconnect raise
  `WifiUnsupportedOperation` and accept no credential fields.
- Added 11 fixture-driven adapter/command tests; total suite is 256 tests.

## Review fixes

- Preserved Windows BSSIDs.
- Corrected escaped/unescaped `nmcli` delimiter parsing.
- Corrected `disconnected` status classification.
- Scoped Linux status commands to the requested interface.
- Made subprocess cancellation terminate the child process.
- Distinguished unsupported read-only operations from unavailable adapters.

## Validation

`pytest -q` passed with 256 tests; Ruff passed; strict mypy passed across 42
source files; `git diff --check` passed.

## Next

Build the TUI network picker and live-session orchestration over the adapter
boundary. Keep subprocess/platform code outside `tui/`, add session-generation
and cancellation guards, and persist only redacted network/connection context.
