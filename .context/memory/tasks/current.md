# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
check its session entry and backlog before starting.

- **Session:** —
- **Task:** none — no session in progress. Last completed: Session 12 (2026-08-02) — `src/` aligned with ADR-15/17 (single `AcquisitionPolicy.authorized` flag, `--i-have-authorization` + `authorize` verb + AuthorizationGrant machinery removed, `SecurityFinding` fields optional, renderers + tests + docs updated; 199 tests, ruff + mypy clean).
- **Status:** idle
