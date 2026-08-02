# Session Summary (compressed history — entries are removable)

One compact entry per session, newest at the bottom. Unlike
`agents/sessions.md` (the formal registry, append-only forever), this
file is a **working summary**: entries may be removed when a session is
no longer useful, and older detail is expected to compress over time.

The purpose is **continuity, not archival completeness**. A future agent
should understand at a glance what important work happened recently,
what significant decisions were made, and where to find detail if needed.

Entries are separated by `---` so agents can parse them as discrete
records.

<!-- TEMPLATE — copy below the last entry:
---
- **YYYY-MM-DD — Session N** — <agent> / <model> — <one-line outcome>.
  <Key decision or discovery, if any.>
  Detail: .context/memory/sessions/YYYY-MM-DD-N/notes.md (or "summary only").
-->

---
- **2026-07-23 — Session 1** — Super Z / unknown (GLM family) — bootstrapped `.context/` (core 0.2.0) + shipped the PortalLens MVP scaffold (Portal abstraction, captive_wifi analyzer, evidence-backed reporting). 55 tests; validated on the real ISPMan URL pair (maz.wifi → captive.ispman.tech).
  Detail: summary only.

---
- **2026-07-23 — Session 2** — Claude Code / claude-opus-4-8 — replaced per-provider branches with a declarative signature registry (ADR-5/6). Provider knowledge is now data in `signatures.py`. Caught a duplicate-relationship defect by diffing rendered output against a pre-refactor worktree. 55 → 80 tests.
  Detail: summary only.

---
- **2026-07-23 — Session 3** — Claude Code / claude-opus-4-8 — decisions-only session: recorded ADR-7..13 (TUI, persisted Investigation, AnalysisStep registry, per-technique authorization, SecurityCheck registry, assess-not-exploit, consent tiers) + 7 backlog items.
  Detail: summary only.

---
- **2026-07-23 — Session 4** — Super Z / unknown (GLM family) — implemented ADR-7: the investigation-console TUI (Textual, responsive ~40 cols → desktop, optional extra). CLI became a click.Group. 102 tests.
  Detail: summary only.

---
- **2026-07-23 — Session 5** — Claude Code / claude-opus-4-8 — implemented ADR-8: persisted `Investigation` (SQLite, document-in-SQLite + migration ledger, ADR-14). Four CLI verbs (investigate/investigations/show/authorize). 102 → 135 tests.
  Detail: summary only.

---
- **2026-07-23 — Session 6** — GitHub Copilot / DeepSeek V4 Flash Free — Phase-1 setup on Windows 11; recorded the Windows environment; documented pre-existing path-separator test failures. No feature target.
  Detail: summary only.

---
- **2026-07-23 — Session 7** — Claude Code / claude-opus-4-8 — ADR-9 first slice: structured `OpenQuestion` model (subject, edge kind, question, `resolves_with` slugs). Model + migration only. 138 tests.
  Detail: summary only.

---
- **2026-07-23 — Session 8** — GitHub Copilot / DeepSeek V4 Flash Free — Windows E2E validation of all 6 CLI commands + cp1252 Unicode fix (followed by a second-wave fix; the output-boundary `console_safe`/`echo` commit 2bc6872 landed after — encoding now handled at emit, not in source strings). 138 → 146 tests.
  Detail: summary only. (Note: two sessions both logged as "Session 8" on 2026-07-23 — concurrent Windows agents; see agents/sessions.md.)

---
- **2026-08-01 — Session 9** — Buffy / deepseek-v4-flash — synced `.context/` (core 0.3.0 → 0.5.0) + initialized portallens on macOS (editable install, ruff/mypy/146 tests green, E2E CLI smoke on the fixture pair). First session on core 0.5.0 — created the `memory/sessions/` module.
  Key discovery: 0.5.0 adds session-scoped memory + `context-sync.ps1` (Windows port, as-yet unexercised outside the package repo).
  Detail: .context/memory/sessions/2026-08-01-9/notes.md

---
- **2026-08-02 — Session 11** — Buffy / deepseek-v4-flash — records-only security-constraint relaxation: ADR-15 (one authorization unlocks all active techniques, supersedes ADR-1/10/13), ADR-16 (assess/exploit ban lifted — nothing built, supersedes ADR-12), ADR-17 (disclosure schema optional). Code alignment backlogged.
  Detail: .context/memory/sessions/2026-08-02-11/notes.md

---
- **2026-08-02 — Session 12** — Buffy / deepseek-v4-flash — aligned `src/` with ADR-15/17: `AcquisitionPolicy` is one `authorized` boolean; `--i-have-authorization` + `authorize` verb + AuthorizationGrant machinery removed; `analyze`/`tui`/`investigate`/`step` share `--authorized`; `SecurityFinding` prose fields optional with renderers tolerant (ADR-17). 199 tests, ruff + mypy clean. Backlog item checked off; ADR-15/17 notes updated.
  Detail: .context/memory/sessions/2026-08-02-12/notes.md

---
- **2026-08-02 — Session 13** — Buffy / deepseek-v4-flash — shipped bounded authorized captive-portal bypass probes (CONNECT, DNS tunnel, click-through, port scan, parameter tampering), typed bypass evidence, and report-level potential-bypass findings via `detect_bypass` / `merge_bypass_evidence`. 220 tests, Ruff, mypy clean.
  Key decision: keep probes caller-driven and passive by default; open ports remain informational prerequisite evidence, not bypass proof. Product commit c23f0e6 pushed.
  Detail: .context/memory/reviews/2026-08-02-review.md

--
- **2026-08-02 — Session 14** — Buffy / deepseek-v4-flash — refined the kickoff feature list against existing ADRs (ADR-15 single-auth model, ADR-16 per-action discipline, ADR-18 probe-only "never authenticate" boundary). Plan-only — no `src/` commits. Six backlog entries appended; ADR-19 drafted as the three-category per-action exemplar for session replay (synthetic / owned-target approved; captured-real refused). Items that cross ADR-18 (default creds, MAC impersonation, captured-real replay) explicitly routed through per-action ADR-16 review before any code may land.
  Detail: .context/memory/sessions/2026-08-02-14/notes.md

---
- **2026-08-02 — Session 15** — Buffy / deepseek-v4-flash — docs: README Usage condensed to a quick-start summary + new full tutorial `docs/TUTORIAL.md` (every command with options, report format, TUI, saved investigations, `--authorized`, five bypass probes, library API, troubleshooting). Reviewer caught + fixed one factual error (`--db` listed on `analyze`) and an unverified TUI quit key. 220 tests still green; nothing behavior-changing.
  Detail: .context/memory/reviews/2026-08-02-review-2.md

- **2026-08-02 — Session 16** — Buffy / deepseek-v4-flash — TUI upgraded from static report viewer to a live investigation console over the `Investigation` aggregate: StatusBar (AUTH badge + MODE + live evidence/findings/open-question counters), streaming activity feed, keyboard controls (1-9 next-steps, probe, monitor, auto, save, export, refresh), single-flight workers + evidence dedupe, monitor/auto-run modes, `--auto`/`--monitor`/`--monitor-interval` flags, auto-save at launch. Post-push reviewer caught 3 concurrency bugs (wedged busy on worker exception, duplicate monitor evidence, dual exclusive workers racing the busy flag) — fixed with regression tests in 6056dfc. 231 tests green; ADR-7/ADR-15 invariants held.
  Detail: .context/memory/reviews/2026-08-02-review-3.md

---
- **2026-08-02 — Session 17** — Buffy / deepseek-v4-flash — shipped the first safe Wi-Fi foundation slice in `portallens.wifi`: credential-free immutable network/connection models, lifecycle states, cancellation, capability/error types, adapter protocol, and persistence-safe redaction. ADR-20 records the contract-first decision; reviewer caught and fixed sensitive portal URL/error persistence risk. Product commit `ec62769`; 245 tests green, Ruff/mypy clean.
  Detail: .context/memory/reviews/2026-08-02-feature-review.md
