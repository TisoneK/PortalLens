# Review — Wi-Fi picker and session controller (2026-08-02)

## Scope

This slice adds a read-only `portallens wifi` command and a hardware-
independent session controller over the existing desktop adapters. It supports
scan, rescan, cancellation, generation-guarded stale-result rejection, and
network selection. It does not connect to networks, accept credentials, open a
browser, detect portals, or invoke bypass actions.

## Implementation

- `src/portallens/wifi/session.py` provides immutable picker states and a
  thread-safe `WifiSessionController` with a single scan worker, cancellation
  token propagation, monotonic generations, public listener replacement, and
  selection validation.
- `src/portallens/wifi/picker.py` provides the lazy Textual `WifiPickerApp`.
  `r` rescans, `c` cancels, Enter selects, and `q` exits. Network labels escape
  SSIDs/BSSIDs before Rich markup rendering. Stale rows are cleared at scan
  start and listener delivery is detached safely on unmount.
- `portallens wifi --platform ... --interface ...` creates the appropriate
  adapter and launches the picker. Core `portallens.wifi` imports remain
  Textual-free; the picker is imported only by the command or explicitly by
  callers.
- The controller has no credential fields and never calls `connect` or
  `disconnect`.

## Review fixes addressed

- Rejected selection unless the current scan is ready.
- Added an initial-state constructor seam for deterministic tests.
- Seeded generation counters from initial state.
- Removed fragile future bookkeeping and the fast-completion race.
- Added safe callback handling during Textual shutdown.
- Cleared stale UI rows during rescans.
- Kept Textual lazy and core imports dependency-free.
- Corrected Python 3.10 typing compatibility without adding a transitive
  dependency.

## Validation

- `pytest -q`: **263 passed**
- Ruff: clean
- strict mypy: clean across **44 source files**
- `git diff --check`: clean
- `portallens wifi --help`: verified
- `import portallens.wifi`: verified without loading Textual

## Follow-up

The next slice is captive-portal detection for a selected, host-mediated Wi-Fi
session. It should remain bounded to connectivity-probe status/redirect
capture and feed passive analyzer inputs; it must not open a browser or invoke
bypass automation.
