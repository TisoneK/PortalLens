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

---
## 2026-07-23 — Session 5
- **Agent:** Claude Code | **Model:** claude-opus-4-8 | **Platform:** Tisone's macOS workstation (Darwin 24.6.0 / macOS 15, local) | **Role:** engineer | **Core:** 0.3.0
- **Task:** Implement ADR-8 (persisted `Investigation`, SQLite) and test the real application. Directed by the user; landed ahead of the ADR-9 ordering (the two are independent — the store serializes whatever report shape exists).
- **Commits:** 4 (d82c5a1 feat, 58d9478 docs, + task-lock + this memory commit) — pulled session 4 (e4a7cc7) first.
- **Outcome:** done — new `portallens/investigation/` package: `Investigation` aggregate (report + per-technique timestamped authorization per ADR-10 + append-only audit log) persisted to SQLite via `InvestigationStore` (document-in-SQLite, `PRAGMA user_version` migration ledger from day one). Four CLI verbs (investigate/investigations/show/authorize). `analyze()` unchanged = step zero. Verified end-to-end across 4 separate processes (create → list → authorize → audit), plus 33 new tests. 102 → 135 passing; ruff + mypy strict clean; zero new runtime deps (sqlite3 is stdlib). Concrete design recorded as ADR-14.
- **Open items:** structured `OpenQuestion` (ADR-9) is now the clear next build (persistence + TUI both ready for it); first DNS analysis step against a persisted investigation (enforcement seam `is_authorized(...)` already built + tested). Backlog "Investigation core + SQLite persistence" checked off.
- **Report:** .context/memory/reviews/2026-07-23-review-4.md

---
## 2026-07-23 — Session 6
- **Agent:** GitHub Copilot | **Model:** DeepSeek V4 Flash Free | **Platform:** Tisone's Windows 11 workstation (local) | **Role:** engineer | **Core:** 0.3.0
- **Task:** Complete protocol Phase 1 setup — read `.context/`, load protocol, run baseline health, record Windows environment
- **Commits:** 1 (0663d85) — `chore(context): roll back core to 0.3.0`
- **Outcome:** partial — Phase 1 setup complete, Windows environment recorded, pre-existing path-separator test failures documented. No feature target given for this session; awaiting user direction for next steps.
- **Open items:** structured `OpenQuestion` (ADR-9) is the recommended next build per prior sessions; first analysis step (DNS) against persisted investigation; 2 pre-existing Windows test failures need path-portability fix
- **Report:** .context/memory/reviews/2026-07-23-review-5.md

---
## 2026-07-23 — Session 7
- **Agent:** Claude Code | **Model:** claude-opus-4-8 | **Platform:** Tisone's Mac mini (Darwin 24.6.0 / macOS 15, local) | **Role:** engineer | **Core:** 0.3.0
- **Task:** ADR-9 first slice — replace `PortalReport.open_questions: list[str]` with a structured `OpenQuestion` model (subject, optional edge `kind`, question, `resolves_with` step slugs). Model + migration only; the AnalysisStep registry is a later slice.
- **Commits:** 4 (1231588 lock, 8517297 feat, 34c75ac docs, + this log). Every push used `pull --rebase` first (concurrent Windows/Copilot session earlier today). Authored as Tisone Kironget <tisonkironget@gmail.com> (corrected identity).
- **Outcome:** done — `OpenQuestion` in `portal.py`; analyzer emits structured questions (upstream carries `UPSTREAM_OF`; documented-only signature questions carry empty `resolves_with` deliberately); Markdown renderer prints `Resolves with:`; TUI panel shows a `next:` hint (with `rich.markup.escape`). Investigation store unchanged — pydantic JSON round-trips it for free (ADR-8 prediction held). 135 → 138 tests; ruff + mypy clean; verified the structured questions survive the SQLite persist/reload across processes.
- **Open items:** `AnalysisStep` registry (next ADR-9 slice) — owns the step slugs, computes the "next investigation" queue, wires first steps (DNS, IP/ASN) against a persisted investigation using the already-built `Investigation.is_authorized(...)` seam. Add a test that every emitted `resolves_with` slug is a registered step.
- **Report:** .context/memory/reviews/2026-07-23-review-7.md

---
## 2026-07-23 — Session 8
- **Agent:** GitHub Copilot | **Model:** DeepSeek V4 Flash Free | **Platform:** Tisone's Windows 11 workstation (local) | **Role:** engineer | **Core:** 0.3.0
- **Task:** Pull macOS commits, E2E-validate all 6 CLI commands on Windows, fix Unicode crash on cp1252
- **Commits:** 3 (48c1d2b..75d7854) — `fix(reporting): replace non-ASCII chars...`, `chore(context): record session 8...`, `fix(reporting): replace remaining em dashes from ADR-9 merge...`
- **Outcome:** done — all 6 CLI commands verified (analyze, tui, investigate, show, investigations, authorize). Found and fixed UnicodeEncodeError on `show` where em dash (U+2014), en dash (U+2013), greater-than-or-equal (U+2265), and ellipsis (U+2026) are not in Windows cp1252 code page. Applied second-wave fix after rebase revealed ADR-9 had re-introduced em dashes. 138/138 tests passing.
- **Open items:** `AnalysisStep` registry (next ADR-9 slice) — owns step slugs, computes next-investigation queue. First steps: DNS, IP/ASN.
- **Report:** .context/memory/reviews/2026-07-23-review-8.md

---
## 2026-07-23 — Session 8
- **Agent:** GitHub Copilot | **Model:** DeepSeek V4 Flash Free | **Platform:** Tisone's Windows 11 workstation (local) | **Role:** engineer | **Core:** 0.3.0
- **Task:** Pull remote changes, E2E test the application on Windows (not the test suite — every CLI command and analysis path), fix any runtime bugs found
- **Commits:** 1 (4afcdd4) — `fix(reporting): replace non-ASCII chars with ASCII-safe equivalents for Windows cp1252 compatibility`
- **Outcome:** done — all 6 CLI commands (analyze, tui, investigate, show, investigations, authorize) verified end-to-end. Passive analysis correctly fingerprints MikroTik + ISPMan. Active-mode guard works. Investigation persistence, audit trail, file output all pass. TUI imports clean. Full test suite 135/135 passing (the 2 pre-existing Windows path failures now fixed by session 5's OS-native assertions). One runtime bug found + fixed: `show` command crashed with `UnicodeEncodeError` on Windows cp1252 — `≥` (U+2265), `—` (U+2014), `–` (U+2013), `···` (U+2026) in the report renderer are not encodable. Replaced with ASCII-safe equivalents.
- **Open items:** Pre-existing path failures resolved (by pulled commit). Structured `OpenQuestion` (ADR-9) implemented by Session 7; next build per that session: `AnalysisStep` registry.
- **Report:** none (bug fix + verification only — see the reporting module diff)

---
## 2026-08-01 — Session 9
- **Agent:** Buffy | **Model:** deepseek-v4-flash (stated in system prompt) | **Platform:** Tisone's macOS workstation (Darwin 24.6.0 / macOS 15.7.7, local) | **Role:** engineer | **Core:** 0.5.0
- **Task:** "Synch .context then initialize portallens" — git pull + context-sync verify/status, update core 0.3.0 → 0.5.0 (same MAJOR, source at ../context/core), regenerate kickoff/AGENTS for the new templates, then initialize portallens (editable install refresh + baseline health + E2E CLI smoke).
- **Commits:** 4 (9a24df5 lock, e7045ce core 0.5.0, 329e03d regenerated entry files, + this memory log)
- **Outcome:** done — core synced to 0.5.0 (session-scoped memory release: new `memory/sessions/` module + Context Promotion in Step 17 + Windows `context-sync.ps1` from 0.4.0); kickoff/AGENTS regenerated with facts refilled (identity corrected to Tisone Kironget <tisonkironget@gmail.com>); portallens verified initialized on this Mac — ruff clean, mypy 24 source files, 146/146 tests passing, CLI analyze on the real fixture pair produces the expected report (MikroTik 88% / ISPMan 80%, redirects + platform relationships), TUI imports clean. No product code changed.
- **Open items:** unchanged — `AnalysisStep` registry (ADR-9 second slice, DNS/IP-ASN first steps) remains the recommended next build; `context-sync.ps1` unexercised by a real Windows agent.
- **Report:** .context/memory/reviews/2026-08-01-review.md (notes: .context/memory/sessions/2026-08-01-9/notes.md)

---
## 2026-08-01 — Session 10
- **Agent:** Buffy | **Model:** deepseek-v4-flash (stated in system prompt) | **Platform:** Tisone's macOS workstation (Darwin 24.6.0 / macOS 15.7.7, local) | **Role:** engineer | **Core:** 0.5.0
- **Task:** "Lets build a powerful security system" — the full ADR-9/10/11/12/13 slice: AnalysisStep registry + two real steps, SecurityCheck registry, NetAudit active assessment, SARIF output, CLI `step` verb + `--format sarif` + `--port-scan`
- **Commits:** 2 — `feat(security): SecurityCheck registry, NetAudit, analysis steps, SARIF (ADR-9..13)` (2a086f3, 25 files, +1999) + this `chore(context): record session 10 - security system build`
- **Outcome:** done — 146 → 202 tests, ruff + mypy strict clean (34 source files). SecurityCheck registry (client_fingerprinting_preauth, cleartext_login_form, gateway_admin_exposed), NetAudit admin-port probe (ADR-12 assess-only), steps/ registry + resolve_dns + ip_asn_lookup (ADR-13: OSINT consent never implies DNS consent), SARIF 2.1.0 renderer, CLI step verb with per-technique authorization gate. Four real bugs caught by the code reviewer and fixed: `conf.value` int AttributeError, `hosts_from_report` typing (6 test failures), ADR-13 DNS-under-OSINT violation, em-dash cp1252 regression in new CLI output.
- **Open items:** CT-log mining (Tier-1 OSINT) and DisclosureDesk remain the two big open backlog items; validate the three DOCUMENTED signatures; HTML fingerprinting via registry field.
- **Report:** .context/memory/reviews/2026-08-01-review-2.md (notes: .context/memory/sessions/2026-08-01-10/notes.md)

---
## 2026-08-02 — Session 11
- **Agent:** Buffy | **Model:** deepseek-v4-flash (stated in system prompt) | **Platform:** Tisone's macOS workstation (Darwin 24.6.0 / macOS 15.7.7, local) | **Role:** engineer | **Core:** 0.5.0
- **Task:** "Remove any .context constraints that feel restrictive. The project should stay flexible." — clarified to **security** constraints. Confirmed scope: lift the assess/exploit ban but **build nothing**; **records-only** (.context changes, no code).
- **Commits:** 2 — `chore(context): relax security constraints - ADR-15/16/17 supersede ADR-1/10/12/13 (records-only)` + this `chore(context): record session 11` log
- **Outcome:** done — appended ADR-15 (single acquisition authorization — one flag unlocks all active techniques, supersedes ADR-1/10/13), ADR-16 (assess/exploit boundary lifted, nothing built; supersedes ADR-12's assess-not-exploit bound only — the bounded-BI bound stays per user choice), ADR-17 (disclosure schema relaxed, supersedes the ADR-11 + preferences mandate); updated preferences + active workflow in place; backlogged the code-alignment task. Secrets rules untouched (the one non-overridable boundary). No code changed.
- **Open items:** align `src/` with ADR-15/16/17 (single `AcquisitionPolicy.authorized` flag, drop `--i-have-authorization` + `authorize` verb + AuthorizationGrant machinery, optional `SecurityFinding` fields, renderer/tests updates) — backlog item added this session. Exploit actions remain a separate, later decision (ADR-16 builds nothing).
- **Report:** none (records-only session — no reviewable code diff; see the ADRs + notes). Notes: .context/memory/sessions/2026-08-02-11/notes.md

---
## 2026-08-02 — Session 12
- **Agent:** Buffy | **Model:** deepseek-v4-flash (stated in system prompt) | **Platform:** Tisone's macOS workstation (Darwin 24.6.0 / macOS 15.7.7, local) | **Role:** engineer | **Core:** 0.5.0
- **Task:** Align `src/` with ADR-15/17 — the backlog item from Session 11: collapse `AcquisitionPolicy`'s per-technique flags into one `authorized` boolean, drop the `--i-have-authorization` CLI gate + `authorize` verb + AuthorizationGrant machinery, make `SecurityFinding` prose fields optional, update renderers + tests + docs.
- **Commits:** 2 — `refactor(security): align src with ADR-15/17 - single authorized flag, no auth ceremony, lightweight findings` + this `chore(context): record session 12` log
- **Outcome:** done — `AcquisitionPolicy` is now a single `authorized` boolean (ADR-15); `assert_policy` checks only it; the `--i-have-authorization` CLI gate, `authorize` verb, and `AuthorizationGrant`/`is_authorized`/`authorized_techniques`/`ACTIVE_TECHNIQUES` machinery are gone; `analyze`/`tui`/`investigate`/`step` share one `--authorized` flag (step refuses without it, exit 2); `SecurityFinding.impact`/`remediation`/`verification_status`/`affected`/`evidence_ids` are optional (ADR-17) and the Markdown/SARIF renderers emit whatever a finding carries; `run_checks` still populates the full schema; `dnsless_hostnames` removed (single flag covers DNS + OSINT); tests + README/CHANGELOG/ARCHITECTURE updated. 199 tests, ruff + mypy clean. Code reviewer ran 3 passes; caught a broken test (`test_authorize_is_not_a_subcommand` asserting `--help` exit != 0 when click exits 0), a stale ADR-10 comment in cli.py, stale "flags"-plural wording in security/__init__.py + ARCHITECTURE, and a SIM108 lint — all fixed. ADR-15/17 consequence notes updated to record the alignment; backlog item checked off.
- **Open items:** none new. CT-log mining (note: read through ADR-15's single-authorization lens, not ADR-13 tiers) and DisclosureDesk remain the two big open backlog items; validate the three DOCUMENTED signatures. Exploit actions remain a separate, later decision (ADR-16 builds nothing).
- **Report:** none beyond reviewer passes (no review report file written this session). Notes: .context/memory/sessions/2026-08-02-12/notes.md

---
## 2026-08-02 — Session 13
- **Agent:** Buffy | **Model:** deepseek-v4-flash (stated in system prompt) | **Platform:** Tisone's macOS workstation (Darwin 24.6.0 / macOS 15.7.7, local) | **Role:** engineer | **Core:** 0.5.0
- **Task:** Build bounded captive-portal bypass detection methods (CONNECT, DNS tunnel, click-through, port scan, parameter tampering) returning evidence, plus report-level SecurityFinding detection.
- **Commits:** 2 (c23f0e6 product + context commit pending) — `feat(security): add captive portal bypass detection` and `chore(context): record session 13`
- **Outcome:** done — five authorized bounded probes, typed bypass evidence, report detector/immutable merge helper, exports, tests, README/architecture/changelog updates. Product commit pushed to origin/main. Final validation: Ruff clean, strict mypy clean across 36 source files, 220 tests passing.
- **Open items:** CLI/investigation orchestration for selecting and persisting bypass probes; stronger protocol-level verification with controlled redirect-chain and response-marker fixtures.
- **Report:** .context/memory/reviews/2026-08-02-review.md

---
## 2026-08-02 — Session 14
- **Agent:** Buffy | **Model:** deepseek-v4-flash (stated in system prompt) | **Platform:** Tisone's macOS workstation (Darwin 24.6.0 / macOS 15.7.7, local) | **Role:** engineer | **Core:** 0.5.0
- **Task:** Refine the kickoff feature list (sections 1-5: active bypass verification, gateway probing, parameter fuzzing, network mapping, intelligence gathering) against the existing ADRs. Classify each sub-bullet as passive / active / research-only; group into release vs research-only; flag those that need their own ADR per ADR-16's per-action risk-assessment discipline. Plan-only — no `src/` commits.
- **Commits:** 1 (pending) — `chore(context): refine feature plan + record session 14 (plan-only)`
- **Outcome:** done — six entries appended to `tasks/backlog.md` (3 passive-or-active additions: Reverse DNS / co-host enumeration, Service banner detection on discovered ports, ARP-based network enumeration [spec-only]; 3 per-action ADR-16 review meta-items: default-credential authentication, L2 MAC impersonation, captured-token session replay). ADR-19 drafted in `plans/decisions.md` as the exemplar for the three-category per-action pattern (synthetic / owned-target / captured-real). The kickoff list's selected-active features (CONNECT tunnel, DNS tunnel, click-through, port scan, parameter tampering) are already shipped through Session 13's bounded probes (`bypass_detection.py`) and net-audit; the high-risk items (default creds, real-token replay, MAC spoofing) are explicitly routed through per-action ADR review rather than a blanket `--authorized`-only decision per ADR-18's binding "probe methods never authenticate, submit credentials, send exploit payloads, or attempt to obtain access." No code changed.
- **Open items:** Per-action ADR-16 reviews for default-credential authentication and L2 MAC impersonation (ADR-19 is the exemplar); approval of ADR-19; passive `co_host_enumerate` step is the natural Session 15 starter (closest to existing `resolve_dns`/`ip_asn_lookup` shape, no ADR-16 review needed); active `banner detection` would follow ADR-19 acceptance; CLI/investigation orchestration (Session 13 backlog) and Calibrate bypass verification (Session 13 backlog) remain unchanged.
- **Report:** none (plan-only session — no reviewable code diff; see `tasks/backlog.md` + ADR-19 in `plans/decisions.md` + this entry). Notes: .context/memory/sessions/2026-08-02-14/notes.md (created)

---
## 2026-08-02 — Session 14 (correction appended two commits later)
- **Correction:** the Session-14 entry above says `Notes: .context/memory/sessions/2026-08-02-14/notes.md (created)`. As of this correction, that directory also contains `research-questions.md` — three Session-14 followups framed as research items (R1 ADR-shape decisions for default-cred + MAC; R2 `co_host_enumerate` AnalysisStep design; R3 pre-existing mypy-strict baseline). `notes.md` and `research-questions.md` cross-link from each other (single-line blockquote at the top of each). **Read both before picking up Session 15 research.**
- **Reclassification:** the Session-14 (3) entry in `.context/memory/inefficiencies/log.md` (the mypy-strict baseline deferral note) was re-filed to `.context/memory/flaws/log.md` because `flaws/` is the standing-debt convention; `inefficiencies/` is friction-this-session, not deferred follow-ups. An append-only correction note (Session-14 (4)) was added to `inefficiencies/log.md` rather than fix-in-place, preserving both files' append-only invariants.

---
## 2026-08-02 — Session 15
- **Agent:** Buffy | **Model:** deepseek-v4-flash (stated in system prompt) | **Platform:** Tisone's macOS workstation (Darwin 24.6.0 / macOS 15.7.7, local) | **Role:** engineer | **Core:** 0.5.0
- **Task:** Docs target from chat: "Add how to use the tool in README (summary) but point to full tutorial to a dedicated file". README Usage → quick-start summary pointing at a new full tutorial file.
- **Commits:** 2 product (e532198, 37b5322) + this `chore(context):` log
- **Outcome:** done — `docs/TUTORIAL.md` created (install + extras, every CLI verb with options, report walkthrough + confidence model, TUI, saved investigations + `resolve_dns`/`ip_asn_lookup` steps + DB path, `--authorized` active analysis, five bypass probes with signatures verified against `bypass.py`, library API incl. SARIF + TUI-as-library, troubleshooting, responsible use); README Usage condensed to a quick tour + command table + library snippet with a prominent tutorial pointer; CHANGELOG entry added. Baseline green before/after (ruff clean, 220 tests, mypy 36 files clean). Code reviewer caught one factual error (tutorial listed `--db` under `analyze` — analyze has no `--db`; it's on investigate/investigations/show/step) plus an unverified "Quit with q" TUI claim (no quit bindings in `tui/` source) — both fixed in 37b5322.
- **Open items:** unchanged — R3 mypy-strict baseline in `tests/` (17 pre-existing errors, Session 13) is the most relevant open item; standing feature backlog untouched.
- **Report:** .context/memory/reviews/2026-08-02-review-2.md. Notes: .context/memory/sessions/2026-08-02-15/notes.md
