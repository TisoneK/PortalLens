# Session 16 — live investigation-console TUI (2026-08-02)

> **Adjacent file:** the review report is at
> `.context/memory/reviews/2026-08-02-review-3.md`.

## Target (user)

"TUI still feels like non-tui its not an advanced hacking tool-like with
live updates and controls." ask_user choices: **all three liveness
modes** (on-demand / auto-run / monitor) + **auto-save at launch**.

## What shipped

- `PortalLensApp` now runs over an `Investigation` (ADR-8), not a bare
  report. CLI `tui` builds the investigation, auto-saves it, and passes
  `--authorized`/`--auto`/`--monitor`/`--monitor-interval`/`--db`.
- StatusBar widget (AUTH badge, MODE badge, live evidence/findings/
  question counters, busy indicator) — text + colour, never colour-only.
- Streaming activity feed (`RichLog`) with timestamps.
- Controls: `1`-`9` run the Nth computed next-step (parameterized
  binding `run_step(i)`), `n` next, `p` admin-port probe, `m` monitor
  toggle, `a` auto-run toggle, `s` save, `e` export Markdown, `r`
  refresh, `q` quit.
- Single-flight execution: ONE `@work(thread=True, exclusive=True)`
  `_action_worker` serves every action — race-free busy flag, and any
  exception (not just `AcquisitionDenied`) logs + clears busy.
- Evidence dedupe by `(type, source, key, value)` in `_apply_evidence`.
- Monitor mode re-issues the admin-port probe on a timer, logging only
  port open/close deltas; requires `--authorized`.
- Open-question closure after actions via the engine's
  `refine_open_questions` + `run_checks` (ADR-9 loop closure) — the
  same recompute the CLI `step` verb does.

## Useful facts for future sessions

- **Textual 8.2.8 API gotchas:** `App.unbind` does NOT exist (keep
  digit bindings static with parameterized actions); `Log` stores plain
  strings (no markup) while `RichLog.write` renders markup; `App._log`
  is an internal method (name the feed method `_feed`); `App.bind`
  needs `ClassVar` for mutable `BINDINGS` under ruff RUF012.
- **No tmux on this Mac** — to live-test a TUI, use `/usr/bin/expect`
  with `TERM=xterm-256color` (write the expect script with `write_file`
  and pass long URLs via env vars; drive keys with `send`).
- The vendor-literal AST test scans tui/ executable strings — keep new
  labels free of vendor hostnames ("admin port probe", "monitor", etc.
  are safe).
- `mypy --strict` cares about bare `list` annotations and override
  signatures (`async def action_quit` because the base is async).

## Process

- Phase 1 + baseline before edits; feature committed + pushed (40917f6),
  reviewer pass (3 real bugs), fixes + regression tests committed
  (6056dfc). 231 tests, ruff + mypy clean, live pty verification.
