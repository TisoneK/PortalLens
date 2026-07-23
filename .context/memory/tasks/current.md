# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
check its session entry and backlog before starting.

- **Session:** 2026-07-23 — Session 7 (Claude Code / claude-opus-4-8, local Mac mini)
- **Task:** feature (ADR-9, first slice) — replace `PortalReport.open_questions: list[str]` with a structured `OpenQuestion` model (`subject`, optional edge `kind`, `question`, `resolves_with: list[step-slug]`). Migrate the analyzer, the Markdown renderer, and the TUI panel; add tests. Scope is the model + migration only — the `AnalysisStep` registry is a separate item; `resolves_with` carries slug strings for now.
- **Status:** in progress
