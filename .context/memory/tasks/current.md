# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
check its session entry and backlog before starting.

- **Session:** 2026-07-23 — Session 5 (Claude Code / claude-opus-4-8, local macOS)
- **Task:** feature — implement ADR-8: `Investigation` as a persisted core concept (SQLite, migrations from day one), owning target + report + per-technique timestamped authorization record (ADR-10) + audit log. `analyze()` is step zero. Wire CLI subcommands to create/list/show/authorize, and exercise the real app end-to-end (persistence across process invocations).
- **Status:** in progress
