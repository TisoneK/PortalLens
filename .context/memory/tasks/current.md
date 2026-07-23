# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
check its session entry and backlog before starting.

- **Session:** 2026-07-23 — Session 2 (Claude Code / claude-opus-4-8, local macOS)
- **Task:** feature — "the portal is centered to a specific provider": ISPMan is hardcoded across `url_parser.py`, `fingerprints.py`, `relationship.py`, and `analyzer.py`. Replace the per-provider branches with a declarative signature registry so any captive-portal platform provider slots in as data, not code.
- **Status:** in progress
