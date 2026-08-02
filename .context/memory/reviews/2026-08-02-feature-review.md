# Feature Review - Wi-Fi investigation foundations (2026-08-02)

## Executive Summary

Implemented the first safe vertical slice of the planned live Wi-Fi investigation feature. The new `portallens.wifi` package defines immutable, credential-free Wi-Fi network and connection snapshots, explicit lifecycle states, adapter capabilities, typed operation errors, cancellation, and a platform-neutral OS-mediated adapter protocol. No platform subprocesses, credentials, packet operations, or automated access attempts were added.

## Design Decisions

- **ADR-20** in `.context/memory/plans/decisions.md`: establish a dependency-free adapter contract before platform implementations; keep credentials and packet-level operations out of the public API; use explicit allow-listed serialization.
- Desktop first remains the scope: Windows, macOS, and Linux adapters will implement the contract in later slices. Mobile restrictions remain a capability concern for a later phase.
- Portal URLs and adapter errors are sanitized at serialization time. Sensitive query keys, nested URL values, opaque token-like path segments, fragments, and raw error text are not persisted.

## What Was Built

- `src/portallens/wifi/models.py`
  - `WifiSecurity` and `WifiConnectionState` enums.
  - Immutable `WifiNetwork` snapshots with BSSID normalization, signal clamping, stable identity, and safe `to_dict()`.
  - Immutable `WifiConnection` snapshots with validated lifecycle transitions, interface propagation, captive-portal URL invariants, and redacted serialization.
  - `WifiAdapterCapabilities` and thread-safe `CancellationToken`.
- `src/portallens/wifi/adapter.py`
  - Runtime-checkable `WifiAdapter` protocol for scan, OS-mediated connect, status, disconnect, and cancellation.
  - Capability gate helper.
- `src/portallens/wifi/errors.py`
  - Typed adapter-unavailable, permission, unsupported-operation, timeout, cancellation, and connection errors.
- `src/portallens/wifi/__init__.py`
  - Public exports without adding dependencies or importing the TUI.
- `tests/test_wifi.py`
  - 14 hardware-independent tests covering normalization, state transitions, cancellation, capabilities, protocol conformance, serialization allow-lists, and credential redaction.

## What Was Verified

- `pytest -q tests/test_wifi.py` - 14 passed.
- `ruff check src/portallens/wifi tests/test_wifi.py` - passed.
- `mypy src/portallens` - passed, 40 source files.
- `pytest -q` - 245 passed.
- `git diff --check` - passed.
- Public-symbol search confirmed the new symbols have no existing callers requiring migration.

## What Was Not Verified

- No live Wi-Fi hardware was touched.
- Windows Native Wi-Fi, macOS CoreWLAN, and Linux NetworkManager adapters are not implemented yet.
- No TUI network picker, OS connection request, captive-portal probe, or live SQLite event stream is included in this slice.
- Platform permission behavior and localized command/API output remain for the adapter implementation slices.

## Open Items / Backlogged Findings

- Implement deterministic Windows/macOS/Linux discovery adapters using captured fixtures and capability reporting.
- Add the TUI network picker, cancellation/session generation handling, and target switching.
- Add captive-portal detection and append-only live event persistence.
- Revisit the existing bypass-probe orchestration backlog separately; this feature slice does not invoke bypass probes automatically.
