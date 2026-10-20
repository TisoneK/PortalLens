# Review — deterministic desktop Wi-Fi adapters (2026-08-02)

## Scope

This slice adds read-only Windows, macOS, and Linux Wi-Fi discovery/status
adapters behind the existing credential-free `WifiAdapter` protocol. It does
not associate with networks, accept credentials, capture packets, invoke a
browser, or run bypass actions.

## Implementation

- `src/portallens/wifi/command.py` provides an injectable command boundary.
  Commands use argument arrays with `shell=False`, bounded timeouts, UTF-8
  replacement decoding, typed unavailable/permission/timeout errors, and a
  polling `Popen` loop that kills a process when cancellation is requested.
- `src/portallens/wifi/adapters.py` provides:
  - Windows `netsh wlan show networks mode=bssid` and interface status.
  - macOS `airport -s` and `networksetup -getairportnetwork`.
  - Linux NetworkManager `nmcli` scan and interface-scoped status.
- Parsers normalize hidden SSIDs, BSSIDs, signal values, channels, and security
  classes into the existing domain models and deduplicate scan snapshots.
- All concrete adapters advertise `can_scan`/`can_status` only; connect and
  disconnect raise `WifiUnsupportedOperation`.

## Review findings addressed

- Preserved Windows BSSID fields from structured `netsh` output.
- Added escaped/unescaped delimiter handling for `nmcli` terse output.
- Prevented `disconnected` from being classified as connected.
- Forwarded interface scope to Linux status commands.
- Made cancellation interrupt a running subprocess instead of waiting for the
  command timeout.
- Kept read-only methods distinct from an unavailable adapter error.
- Kept platform command and parser details isolated from the TUI and core
  investigation logic.

## Validation

- `pytest -q`: **256 passed**
- Ruff: clean for the changed Wi-Fi source and tests
- strict mypy: clean across **42 source files**
- `git diff --check`: clean

## Follow-up

The next feature slice remains the TUI network picker and live-session
orchestration. It should consume this adapter boundary, maintain cancellation
and session-generation guards, and persist only redacted network/connection
context through the investigation aggregate.
