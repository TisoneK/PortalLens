# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
check its session entry and backlog before starting.

- **Session:** —
- **Task:** none — no session in progress. Last completed: Session 11 (2026-08-02) — records-only security-constraint relaxation (ADR-15/16/17 supersede ADR-1/10/12/13 + disclosure-schema mandate; preferences + workflow updated; no code changed). Recommended next: align `src/` with ADR-15/16/17 (single `AcquisitionPolicy.authorized` flag, drop auth ceremony, optional finding schema) — see backlog.
- **Status:** idle
