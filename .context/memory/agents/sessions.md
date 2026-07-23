# Agent Sessions (append-only)

One entry per agent session, newest at the bottom. Never edit or delete
past entries — append corrections instead.

<!-- TEMPLATE — copy below the last entry:
---
## YYYY-MM-DD — Session N
- **Agent:** <name> | **Model:** <model id> | **Platform:** <machine/sandbox + OS> | **Role:** <engineer, or overlay from .context/core/roles/> | **Core:** <version from .context/core/VERSION>
- **Task:** <what this session set out to do>
- **Commits:** <count> (<first-sha>..<last-sha>)
- **Outcome:** <done / partial / blocked — one line>
- **Open items:** <pointers into tasks/backlog.md, or "none">
- **Report:** .context/memory/reviews/YYYY-MM-DD-review.md
-->

---
## 2026-07-23 — Session 1
- **Agent:** Super Z | **Model:** unknown (GLM family) | **Platform:** Z.ai cloud sandbox (Linux, ephemeral) | **Role:** engineer | **Core:** 0.2.0
- **Task:** Bootstrap `.context/` on the empty PortalLens repo and implement the MVP scaffold — `Portal` core abstraction + `captive_wifi` passive analyzer + evidence-backed reporting
- **Commits:** 2 (c59cd5e..84fea3b) — `chore(context): bootstrap .context/ (core 0.2.0)` + `feat(core): PortalLens MVP — Portal abstraction + captive_wifi analyzer`
- **Outcome:** done — MVP scaffold shipped, 55/55 tests passing, ruff + mypy strict clean, validated end-to-end on the real ISPMan URL pair (maz.wifi → captive.ispman.tech). Analyzer correctly produces ISPMan 80% / MikroTik 78% fingerprints, infers redirect (75%) + USES_PLATFORM (80%) + AUTHENTICATES_FOR (75%) + OPERATES_NETWORK (74%), flags RESELLS_BANDWIDTH as a 35% hypothesis, lists open questions for upstream-ISP identification and admin-interface exposure.
- **Open items:** 7 items in `tasks/backlog.md` — NetAudit module, DisclosureDesk module, CoovaChilli fixture, HTML fingerprinting, DNS resolution, IP/ASN lookup, SARIF output.
- **Report:** .context/memory/reviews/2026-07-23-review.md

---
## 2026-07-23 — Session 2
- **Agent:** Claude Code | **Model:** claude-opus-4-8 | **Platform:** Tisone's macOS workstation (Darwin 24.6.0 / macOS 15, local) | **Role:** engineer | **Core:** 0.3.0
- **Task:** feature (target from chat: "The portal is centered to a specific provider") — the captive_wifi analyzer was hardwired to ISPMan across four modules. Replace the per-provider branches with a declarative signature registry.
- **Commits:** 7 (b9357ea..06af5d7) — core update to 0.3.0, task lock, `feat(captive_wifi): recognize any portal provider, not just one`, docs, changelog, review report, and this memory update
- **Outcome:** done — provider knowledge moved to `signatures.py` as data; parser, fingerprint scorer, and relationship analyzer name no vendor. Two providers + one gateway added as registry entries only; a test registers a fourth at runtime. Every confidence score on the ISPMan fixture verified unchanged by diffing against a `git worktree` of the pre-refactor commit. That diff caught a real defect: `USES_PLATFORM` and `AUTHENTICATES_FOR` were each emitted twice in every hosted-platform report. Tests 55 → 80; ruff + mypy strict clean.
- **Open items:** 3 appended to `tasks/backlog.md` (validate the 3 documented-only signatures — supersedes session 1's CoovaChilli item; decide where the signature provenance ledger lives; HTML fingerprinting is now a registry field rather than per-vendor detectors). Session-1 items otherwise unaffected. New ADR-5 + ADR-6 in `plans/decisions.md` constrain how future providers are added.
- **Note on the target:** the one-line chat target was ambiguous between "the analyzed portal belongs to a specific provider" and "the analyzer is centered on a specific provider". Read as the latter — the former is already implemented. Work is additive; nothing was removed, so a different reading can be taken from this base.
- **Report:** .context/memory/reviews/2026-07-23-review-2.md

---
## 2026-07-23 — Session 3
- **Agent:** Claude Code | **Model:** claude-opus-4-8 | **Platform:** Tisone's macOS workstation (Darwin 24.6.0 / macOS 15, local) | **Role:** engineer | **Core:** 0.3.0
- **Task:** Record the architectural decisions from the TUI + advanced-security design conversation as ADRs, and anchor them with backlog items. Decisions only — no product code.
- **Commits:** 1 (0e67544) — `chore(context): ADRs for the investigation-console + advanced-security direction`
- **Outcome:** done — ADR-7..13 appended to `plans/decisions.md` (TUI as responsive presentation layer; Investigation as persisted core; analysis-step registry with computed next-steps; per-technique timestamped authorization; SecurityCheck registry; assess-not-exploit + bounded business intelligence; distinct AcquisitionPolicy consent tiers). 7 anchoring items appended to `backlog.md`. No code changed; suite still 80 (not re-run — no source touched).
- **Open items:** 7 new backlog items (structured OpenQuestion → the recommended first build; Investigation+SQLite; AnalysisStep registry + DNS/IP-ASN; responsive TUI; SecurityCheck registry; CT-log OSINT; client-fingerprinting privacy finding). Recommended order in ADR-9's "build this before any TUI" note and the review-2 sequencing.
- **Note:** ADR-12 is a standing scope/ethics boundary binding now, not a future-implementation decision — future security work must not cross assess→exploit or build org-profiling collectors without a superseding ADR.
- **Report:** none (decisions-only session — see the ADRs directly; no reviewable code diff)

---
## 2026-07-23 — Session 4
- **Agent:** Super Z | **Model:** unknown (GLM family) | **Platform:** Z.ai cloud sandbox (Linux, ephemeral) | **Role:** engineer | **Core:** 0.3.0
- **Task:** Implement ADR-7 — the investigation-console TUI. Pure presentation layer over the engine, Textual, behind `portallens[tui]` extra, responsive ~40 cols → wide desktop, severity never colour-only, no vendor hostnames baked in, CLI becomes a `click.Group`.
- **Commits:** 1 (e06107a) — `feat(tui): investigation-console TUI (ADR-7) — pure presentation, responsive`
- **Outcome:** done — TUI shipped as `src/portallens/tui/` (theme, widgets, app, __init__ shim). `PortalLensApp` renders a `PortalReport` the engine already produced; never calls `analyze()` itself (enforced by test). `RelationshipView` swaps tree-over-detail ↔ side-by-side at `WIDE_THRESHOLD=100` via `on_resize`. CLI is now `_DefaultAnalyzeGroup` with `analyze` + `tui` subcommands; `portallens <urls>` falls back to `analyze` so session-1/2 scripts don't break. `from portallens import PortalReport` stays textual-free (subprocess test enforces it). 22 new tests (102 total); ruff + mypy strict clean. Two first-pass bugs caught by the test suite: `Static.render()` must return `Text` not `str` (Textual 8.x), and `confidence_markup`'s literal brackets needed escaping so `Text.from_markup` didn't parse the badge text as a style tag.
- **Open items:** TUI backlog item closed. Other session-3 items remain open — structured `OpenQuestion` (ADR-9) is the recommended next slice; the TUI's `OpenQuestionsPanel` is a natural consumer once questions carry `resolves_with` step slugs.
- **Report:** .context/memory/reviews/2026-07-23-review-3.md
