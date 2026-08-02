# Architectural Decisions (append-only, ADR-style)

Decisions already made — future agents respect these rather than
relitigating them. To reverse one, append a new ADR that supersedes it.

---
## ADR-1: Passive by default — active analysis requires explicit authorization (2026-07-23)
- **Status:** accepted
- **Context:** PortalLens's value proposition is calibrated, evidence-backed analysis. Active probing (HTTP fetching, DNS resolution, port scanning) of networks the user doesn't own is unauthorized scanning in most jurisdictions. The user explicitly stated in the design conversation: "don't actively scan or probe networks without authorization."
- **Decision:** The default `AcquisitionPolicy` is fully passive. Every active technique is gated behind an explicit per-technique flag (`fetch_urls`, `follow_redirects`, `resolve_dns`, `probe_tls`, `port_scan`). The CLI requires `--i-have-authorization` before any active flag is honored. The active fetcher module (`acquisition/fetcher.py`) is the ONLY place PortalLens reaches outside the process, and it calls `assert_policy(policy, "fetch_urls")` before any network access.
- **Consequences:**
  - Passive analysis (URL parsing + user-supplied HTML/HAR payloads) is always allowed and always safe.
  - Active analysis requires the caller to acknowledge authorization — the library cannot verify it.
  - Confidence scores from passive analysis are interpretable: "this URL signature is X% likely to be MikroTik." Active analysis adds the confound of "the URL might respond differently to a bot vs. a browser" — calibration gets murkier, so active results should be reported separately.
  - Future agents MUST NOT add active techniques without gating them behind an `AcquisitionPolicy` flag and a `--i-have-authorization` CLI flag.

---
## ADR-2: Noisy-OR confidence combination — `score([w1, w2, ...])` (2026-07-23)
- **Status:** accepted
- **Context:** The analyzer needs to combine multiple independent evidence signals into a single confidence score. Three options were considered: max-combination (`max([w1, w2])`), weighted average, and noisy-OR.
- **Decision:** Use noisy-OR: `combined = 1 - prod(1 - w_i / 100)`. Implemented in `portallens.confidence.score`.
- **Consequences:**
  - Two independent medium signals reinforce each other (40 + 40 → 64), which matches intuition — two independent indicators should be stronger than either alone.
  - A single speculative signal never escapes `low` (10 + 10 + 10 → 27), which preserves the integrity of the confidence bands.
  - Two near-certain signals can establish certainty (99 + 99 → 100), which is correct — overwhelming evidence should produce overwhelming confidence.
  - Weighted average was rejected because it dilutes: an 80% signal combined with a 10% signal would drop to 45%, when the 80% signal is what matters.
  - Max-combination was rejected because it doesn't reinforce: two independent 40% signals would stay at 40%, when they should plausibly lift to ~60%.
  - Future agents MUST use `score([...])` for multi-evidence inferences, not ad-hoc arithmetic.

---
## ADR-3: Hypotheses capped at `low` confidence (≤ 39) by convention (2026-07-23)
- **Status:** accepted
- **Context:** The analyzer distinguishes observed facts, inferences, and hypotheses. A hypothesis is "we don't have enough evidence to call this an inference" — if we did, it would be an inference.
- **Decision:** Hypothesis observations (`Observation(kind="hypothesis")`) are capped at confidence 39 (the upper bound of the `low` band). The `RESELLS_BANDWIDTH` relationship is the canonical example — the URL alone cannot distinguish a reseller from an operator using a 3rd-party platform, so it's emitted as a 35% hypothesis, not an inference.
- **Consequences:**
  - The report's "Hypotheses (require verification)" section is always low-confidence — readers know to take those claims as prompts for follow-up, not as findings.
  - The cap is enforced in `CaptiveWifiPortal._hypothesis_observations()` via `min(rel.confidence, 39)`.
  - Test `test_hypotheses_never_exceed_low_confidence` enforces the invariant.
  - Future agents MUST NOT emit hypotheses with confidence > 39. If the evidence supports higher confidence, emit it as an inference instead.

---
## ADR-4: `Portal` is the core abstraction — not `CaptivePortal` (2026-07-23)
- **Status:** accepted
- **Context:** The user explicitly chose `PortalLens` over `CaptiveIntel` as the project name "since we may expand in future to other forms of portals." The core abstraction had to be broad enough to accommodate web auth, payment, and ISP portals without an architectural rewrite.
- **Decision:** The abstract base class is `Portal`, not `CaptivePortal`. The first concrete subclass is `CaptiveWifiPortal`, registered against `PortalType.CAPTIVE_WIFI`. Future portal types (web auth, payment, ISP) register themselves the same way via `@register_portal(PortalType.X)`.
- **Consequences:**
  - The `PortalType` enum reserves `WEB_AUTH`, `PAYMENT`, `ISP` values for future plugins.
  - The `AnalysisContext` carries generic inputs (URLs, HTML/HAR payloads, policy, notes) — not captive-portal-specific fields.
  - The `PortalReport` carries generic outputs (evidence, observations, fingerprints, relationships, open questions) — not captive-portal-specific fields.
  - Future agents adding a new portal type MUST register a `Portal` subclass via `@register_portal` and implement `analyze()`. They MUST NOT add portal-type-specific fields to `Portal`, `AnalysisContext`, or `PortalReport` — those go on the subclass.

---
## ADR-5: Provider knowledge is a registry, not code (2026-07-23)
- **Status:** accepted
- **Context:** The MVP (session 1) hardcoded ISPMan across four modules — an enum member, three module constants, a `_detect_ispman()` function, and six `== "ispman.tech"` comparisons in the relationship analyzer. Adding a second provider meant editing four files and duplicating the relationship reasoning per vendor. ADR-4 established that new *portal types* slot in without a rewrite; nothing established the same for new *providers within a type*.
- **Decision:** Everything PortalLens knows about a captive-portal platform lives in `src/portallens/plugins/captive_wifi/signatures.py` as a `PortalSignature` record: the `SignatureRule`s that decide whether it fires, the weight each matched signal contributes, the display name, and the rule's provenance. The URL parser, the fingerprint scorer, and the relationship analyzer iterate that registry and name no vendor. `signatures.py` is the only module in the plugin that mentions a provider by name.
- **Consequences:**
  - Adding a provider is a registry entry. Verified by a test that registers a provider existing nowhere in the source tree and asserts the parser, scorer, and relationship analyzer all pick it up (`tests/test_signatures.py::TestRuntimeRegisteredProvider`).
  - The registry distinguishes two layers: `SignatureLayer.GATEWAY` (software on the operator's own hardware, identified by the query variables it emits, owns no hostname) and `SignatureLayer.HOSTED_PLATFORM` (a third party running the portal for the operator, identified by its own host + path). This split is what makes `USES_PLATFORM` / `AUTHENTICATES_FOR` / `OPERATES_NETWORK` provider-agnostic — a host owned by any hosted platform is never the network operator.
  - `CaptivePortalURLHints.flavors` holds slug **strings**, not enum members, so a registry entry needs no enum member. `CaptivePortalFlavor` remains as a convenience enum over the built-in slugs; it derives from `str`, so `CaptivePortalFlavor.MIKROTIK in hints.flavors` still works.
  - Host suffix matching goes through `signatures.host_matches()`, which matches on label boundaries — `evilispman.tech` is not ISPMan. Future agents MUST NOT reintroduce a bare `endswith()` host check.
  - Future agents adding provider support MUST add a registry entry. A new `_detect_<vendor>()` function, a new `CaptivePortalFlavor` member, or a vendor hostname compared in `relationship.py` or `analyzer.py` is a regression of this ADR.
  - Confidence scores are unaffected: all four pre-existing detectors were expressible as declarative rules with their original weights, verified by diffing the rendered report against the pre-refactor commit.

---
## ADR-6: Signatures carry provenance; unvalidated ones say so in the report (2026-07-23)
- **Status:** accepted
- **Context:** Generalizing the registry (ADR-5) made adding providers cheap, which creates a new risk: signatures transcribed from vendor documentation can be added faster than they can be validated against real captured URLs. PortalLens's entire value proposition is calibrated, evidence-backed claims (ADR-2, ADR-3). A documentation-derived guess presented identically to a field-validated match would quietly undermine that.
- **Decision:** Every `PortalSignature` records a `Provenance`: `VALIDATED` (a real captured URL matching it lives in this repo's `tests/data/`) or `DOCUMENTED` (transcribed from vendor documentation, never checked against a capture). A `DOCUMENTED` signature still fires and still scores normally, but its fingerprint note states its provenance and the analyzer adds an open question inviting the reader to treat the match as provisional.
- **Consequences:**
  - `MIKROTIK` and `ISPMAN` are `VALIDATED` (the session-1 fixture is a real capture). `COOVACHILLI`, `UNIFI`, and `MERAKI` are `DOCUMENTED`.
  - The cost of adding a speculative signature is paid in the report's noise, which is the correct place for it to be visible.
  - Future agents MUST default a new signature to `DOCUMENTED` and MUST NOT promote one to `VALIDATED` without adding the capture to `tests/data/` that justifies it.
  - Future agents MUST NOT remove the provisional note or open question to tidy up report output. If the noise becomes a problem, the fix is to validate the signature or drop it — not to hide its status.

---
## ADR-7: The TUI is a presentation layer, and it is responsive from phone to desktop (2026-07-23)
- **Status:** accepted (design decision — not yet implemented)
- **Context:** The project will grow an investigation-console TUI. Three risks were identified in the design conversation: (a) scanning/analysis logic leaking into the UI; (b) reorganizing the plugin vertical-slice layout (ADR-4) into function-first packages (`scanners/`, `intelligence/`) to suit the UI, which would spend the plugin boundary on a cosmetic change; (c) a fixed-width layout that assumes a wide desktop terminal. The user explicitly requires the TUI to run on mobile via Termux **and** desktop — a phone in portrait can be ~40 columns.
- **Decision:** The TUI is a pure presentation + control layer. It renders `PortalReport` / `Investigation` state and issues commands to the engine; it contains **no** acquisition, fingerprinting, or inference logic. Built with **Textual**, shipped behind an optional extra (`portallens[tui]`) so the library and CLI keep their `click + httpx + pydantic` dependency set. The layout **must be responsive**: it targets terminals from ~40 columns (Termux, portrait) to wide desktop. Panels reflow and stack rather than assuming width; the relationship graph degrades to an indented/linear form below a width threshold. The plugin vertical-slice structure (`plugins/<type>/`) is preserved — `tui/` and `reports/` are **sibling** cross-cutting layers, not a reorganization of the analyzers.
- **Consequences:**
  - No vendor or example hostname is baked into any screen. `maz.wifi` is a test fixture in `tests/data/` only — never a default, placeholder, or demo value in the UI.
  - Box borders and layout are owned by Textual's layout engine, not hand-drawn with fixed-column box characters (the design mockups overflowed their own borders — that's the failure this rules out).
  - The relationship graph needs an explicit narrow-terminal fallback; it must not assume it can draw a wide node diagram.
  - Severity and status are **never encoded by colour alone** — needed for accessibility and for monochrome terminals (Termux included).
  - A script doing `from portallens... import CaptiveWifiPortal` must not pull Textual. If `cli.py` grows a `tui` subcommand it becomes a `click.Group`; decide that before people script against the current single-command invocation.

---
## ADR-8: `Investigation` is a persisted core concept, shared by the TUI and DisclosureDesk (2026-07-23)
- **Status:** accepted (design decision — not yet implemented)
- **Context:** PortalLens is stateless today (URLs in, report out). The TUI vision (drill-down, history, first-seen / last-scan, incremental steps) needs state. So does the backlogged DisclosureDesk state machine (draft → submitted → acknowledged → fixed → published). Building persistence twice, or building it as a TUI feature, would strand it.
- **Decision:** Introduce `Investigation` as a core, **persisted** concept, stored in **SQLite** (not JSON-on-disk — DisclosureDesk needs queries, and disclosure state wants transactional updates). An `Investigation` owns a target, a growing set of evidence / observations / relationships, an authorization record (ADR-10), and an audit log. `analyze()` becomes the passive bootstrap — "step zero"; further evidence is appended by analysis steps (ADR-9). Persistence is a **core concern shared by the TUI and DisclosureDesk**, not a TUI feature, and is built in core with the TUI as its first consumer.
- **Consequences:**
  - `PortalReport` stays the immutable snapshot / rendering type; `Investigation` is the mutable, persisted aggregate that produces reports.
  - Persistence is built once, in core. Consumers (TUI, DisclosureDesk, CLI) query it; they don't each invent storage.
  - SQLite chosen for queryability and transactional disclosure-state updates. Schema migrations are considered from the first version, not retrofitted.
  - Future agents MUST NOT bolt investigation state onto the TUI layer.

---
## ADR-9: Analysis steps are a registry; the "next investigation" list is computed, not hand-written (2026-07-23)
- **Status:** accepted (design decision — not yet implemented)
- **Context:** The core experience is "pull the thread": DNS → IP → ASN → org; redirect → platform; portal → endpoints. The design surfaced a "NEXT INVESTIGATION →" list. Today `PortalReport.open_questions` is `list[str]` — prose, a dead end you cannot lay out a graph or a menu from.
- **Decision:** Two coupled changes.
  1. **`OpenQuestion` becomes structured** — `subject`, an optional edge `kind` (`RelationshipKind`, e.g. `UPSTREAM_OF` — the edge to draw), the `question` text, and `resolves_with`: a list of **step slugs** that could close it.
  2. **An `AnalysisStep` registry**, parallel to the signature registry (ADR-5). Each step declares: `slug`, `label`, the `AcquisitionPolicy` technique it `requires` (`None` = passive), the `EvidenceType`s it `produces`, and which open-question `kind`s it can `answer`. The "next investigation" list is **computed** by matching currently-open questions to registered steps that can answer them — never hand-maintained. Register an ASN step and every report that ever asked "who's upstream?" gains that action automatically.
- **Consequences:**
  - Steps are **data**, like signatures. No hand-coded per-question UI list; no `if question == "...": offer(...)`.
  - Drill-down chains are step sequences, each consuming the prior step's evidence.
  - Per-technique authorization gating lives on the step's `requires` field (ADR-10).
  - This **supersedes the plain-string open-questions representation**: `analyzer._open_questions()` migrates to emit `OpenQuestion` records. Improves the Markdown too — "what would resolve this" becomes a field rather than four hand-written sentences.
  - Future agents adding an active technique add a registered `AnalysisStep`, not a branch in `analyze()`.

---
## ADR-10: Authorization is per-investigation, per-technique, timestamped, and part of the evidence (2026-07-23)
- **Status:** accepted (design decision — not yet implemented)
- **Context:** Once thread-pulling is the core loop, that loop **is** a sequence of authorization decisions (DNS, TLS, IP/ASN, endpoints — every rung is an active technique, ADR-1). Today `--i-have-authorization` is a single boolean at CLI invocation. For a disclosure report, the authorization assertion is itself part of the evidence — "I asserted authorization for DNS resolution at 14:31 before running it" belongs in the audit trail alongside the findings.
- **Decision:** Authorization is asserted **per investigation, per technique**, and recorded with a **timestamp** inside the `Investigation`'s audit log. It is **not a binary badge** — a user may be authorized to resolve DNS but not to port-scan; scope is a *set* of techniques. Each analysis step checks its technique against the investigation's recorded scope before running. The activity / evidence log is **persisted as the audit trail** — it is what makes a finding defensible weeks later, not ephemeral UI chrome.
- **Consequences:**
  - `AcquisitionPolicy`'s per-technique flags remain the enforcement mechanism (`assert_policy` unchanged); the `Investigation` additionally records **who** asserted **what** and **when**.
  - The TUI `[AUTHORIZED]` indicator shows **scope** (`AUTHORIZED: dns, fetch`), never a bare boolean.
  - No step runs a technique outside the investigation's recorded scope.
  - This audit backbone is what DisclosureDesk builds on.

---
## ADR-11: Security checks are a registry (data), keyed on evidence, not on vendor (2026-07-23)
- **Status:** accepted (design decision — not yet implemented)
- **Context:** Adding "advanced security" invites per-vendor security branches — the exact anti-pattern ADR-5 removed for platform detection, and **worse** here: a check that silently runs against only one provider is a false sense of coverage, which in a security tool is a defect, not just untidy.
- **Decision:** Security checks are a **`SecurityCheck` registry**, parallel to the signature registry. A check is keyed on the **evidence it requires** (e.g. "a login form action over `http://`", "a session identifier in a URL query parameter", "an admin path reachable pre-auth", "device-fingerprinting parameters collected before authentication"), **not** on the platform. Checks run against whatever evidence an investigation holds, regardless of vendor. Provenance (ADR-6) applies: a check derived from a CVE or writeup not reproduced in-repo is `DOCUMENTED`, not `VALIDATED`, and says so in its finding.
- **Consequences:**
  - No `if platform == X: check_Y()`. A new check is a registry entry.
  - Every finding carries the disclosure schema from `user/preferences.md` — Title, Affected asset, Evidence, Impact, **Confidence**, Recommended remediation, Verification status — and the confidence bands / fact-inference-hypothesis split. A confirmed reachable admin panel is a fact at 100; "appears bypassable" without a completed test is a hypothesis capped at low (ADR-3).
  - A check firing on a `DOCUMENTED` basis is marked provisional.
  - NetAudit (backlogged) is where these run, under active `AcquisitionPolicy`.

---
## ADR-12: Assess, never exploit — and keep intelligence reach bounded (2026-07-23)
- **Status:** accepted (this is a standing scope/ethics boundary — binding now, for all future security work)
- **Context:** Every advanced security capability has an exploit twin, and the README's promise that PortalLens "does not bypass authentication" is a defensibility asset, not a limitation. Separately, the "Business" intelligence surface (packages, pricing, payment provider, reseller relationships) risks drifting from "analyze a portal" into "profile an organization" — a different product with different obligations.
- **Decision (two bounds, both binding):**
  1. **Assess, not exploit.** The tool produces **evidence that a condition exists** and stops. Detect that a walled-garden / DNS bypass is possible → yes; perform the bypass → **no**. Detect a reflected or injectable parameter → yes; fire the payload → **no**. Detect an admin panel reachable pre-auth → yes; authenticate to it → **no**. **Auth-bypass detection stops at detection** — consistent with the README's standing promise.
  2. **Bounded business intelligence.** Business structure is inferred **only from evidence the tool already holds for technical reasons** — a payment provider named in a form action, a tier slug in the portal's own URL path, packages listed on a page fetched under authorization. PortalLens does **not** build collectors whose purpose is gathering commercial or organizational information about a target. `RESELLS_BANDWIDTH` stays capped at low (ADR-3); a "Business" view must not present it as a conclusion.
- **Consequences:**
  - Keeps PortalLens inside authorized security testing rather than becoming an attack tool. This is what makes it defensible to build and to run.
  - Future agents MUST NOT add exploit actions, or purpose-built organization-profiling collectors, without a **superseding ADR and explicit user direction**. A later agent tempted to "just make the finding actionable" by exploiting it is violating this ADR.

---
## ADR-13: `AcquisitionPolicy` has distinct consent tiers; enabling one never implies another (2026-07-23)
- **Status:** accepted (design decision — extends ADR-1; not yet implemented)
- **Context:** The advanced techniques span very different risk profiles, and "active" is too coarse a single axis. Certificate-Transparency-log mining touches third parties but **not the target**. Fetching the portal touches the target. Executing the portal's JavaScript can trigger auth flows, submit forms, or spend a voucher — materially more invasive than a fetch.
- **Decision:** `AcquisitionPolicy` gains distinct flags for distinct consent, and **no flag implies another**:
  - **`use_osint_apis`** (or similar) — third-party OSINT / passive intelligence: CT logs, ASN / RIPEstat, passive DNS. Leaves your machine but does **not** touch the target. Distinct from `fetch_urls`.
  - existing **`fetch_urls` / `follow_redirects` / `resolve_dns` / `probe_tls` / `port_scan`** — target-facing active techniques.
  - **`execute_scripts`** — headless-browser JavaScript execution. **Not implied by `fetch_urls`.** Its own capability, and likely its own heavyweight dependency (Playwright, ~300MB) behind an optional extra, plus its own ADR when built.
- **Consequences:**
  - `is_passive` currently means "no target-facing active technique." The OSINT tier needs its own place in that logic — touching third parties is not "passive" even though the target is untouched, so OSINT is neither `is_passive` nor target-facing-active; it is its own middle tier.
  - Each new technique picks the correct tier rather than piggy-backing on `fetch_urls` for convenience.
  - Future agents MUST NOT let `fetch_urls=True` silently enable OSINT calls or script execution.

---
## ADR-14: Investigation persistence is document-in-SQLite with a migration ledger (2026-07-23)
- **Status:** accepted — realizes ADR-8 (which is now implemented in `portallens/investigation/`)
- **Context:** ADR-8 committed to `Investigation` as a persisted core concept in SQLite, but left the storage shape open. The report aggregate (evidence, observations, relationships, open questions) is still evolving — structured `OpenQuestion` (ADR-9) and analysis steps are coming — so a fully-normalized relational schema for it now would be churned repeatedly. Yet DisclosureDesk will need real queries (by target, by disclosure state, by date), which a single opaque blob can't serve.
- **Decision:**
  - **Document-in-SQLite.** Each investigation is one row. The queryable facts — `id`, `target`, `portal_type`, `created_at`, `updated_at` — are promoted to their own indexed columns; the full aggregate is serialized as a JSON document (pydantic `model_dump_json`) in a `data` column. Promoted columns serve queries; JSON gives the aggregate room to evolve. When a new query need appears, a migration promotes another column — it does **not** trigger a rewrite into normalized tables.
  - **Migration ledger from day one.** Schema version lives in SQLite's `PRAGMA user_version`. `_MIGRATIONS` is an ordered list; index *i* migrates to version *i+1*. On connect, every migration past the current version runs, so fresh and old databases converge. A shipped migration is **never edited** — the next change is an append. `SCHEMA_VERSION == len(_MIGRATIONS)`, pinned by a test.
  - **Authorizable-technique set is derived, not hardcoded** — from `AcquisitionPolicy`'s boolean fields (`_active_techniques()`), so ADR-13's future tiers become valid authorization targets with no edit to the investigation code.
  - **Id scheme:** target hostname slug + 6 hex chars (`captive-ispman-tech-1a2b3c`). Human-recognizable, derived from the real target (data, not a hardcoded example), unique across revisits.
- **Consequences:**
  - `PortalReport` stays the immutable snapshot; `Investigation` is the mutable persisted aggregate that owns it.
  - Future agents MUST add schema changes as new entries in `_MIGRATIONS`, never by editing a shipped migration or hand-mutating a live DB.
  - Promoting a column (e.g. `disclosure_state` for DisclosureDesk) is the sanctioned way to make a JSON field queryable — the ledger exists for exactly this.
  - No new runtime dependency: `sqlite3` is stdlib. Persistence must stay dependency-free — do not swap in an ORM without a superseding ADR.

---
## ADR-15: Single acquisition authorization — consent tiers collapsed (2026-08-02)
- **Status:** accepted — supersedes ADR-1 (per-technique gating + `--i-have-authorization`), ADR-10 (per-investigation per-technique authorization records), ADR-13 (consent tiers)
- **Context:** The user directed (2026-08-02): "Remove any .context constraints that feel restrictive. The project should stay flexible." The per-technique consent model — a separate `AcquisitionPolicy` flag per technique (`fetch_urls`, `follow_redirects`, `resolve_dns`, `probe_tls`, `port_scan`, `use_osint_apis`) plus a `--i-have-authorization` CLI gate and per-investigation per-technique authorization records — felt like ceremony that fragments one authorization into many.
- **Decision:** A **single authorization unlocks all active techniques**. One boolean on `AcquisitionPolicy` (e.g. `authorized`, CLI `--authorized`) replaces the per-technique flags; when set, every active technique is permitted; when unset, analysis is fully passive. The `--i-have-authorization` CLI gate and the per-investigation per-technique authorization records are removed. **Passive remains the default** — the single flag defaults off.
- **Consequences:**
  - **Records-level decision made 2026-08-02; code alignment is a separate backlog item.** `src/` still enforces the per-technique model today (flags, `assert_policy(..., technique)`, `investigation.authorize/is_authorized`, the `authorize` CLI verb). A future session aligns the code with this ADR (see backlog).
  - **The ADR-1 architectural invariant stands.** This ADR changes the *consent model*, not the acquisition boundary: `acquisition/fetcher.py` remains the ONLY place PortalLens reaches outside the process, and every active technique still funnels through `assert_policy`. A future agent MUST NOT treat ADR-1 as wholly void — only its per-technique gating and `--i-have-authorization` ceremony are superseded.
  - "Enabling one never implies another" (ADR-13) is gone — one authorization implies all.
  - The audit log stays a defensibility trail (what ran, when); authorization *grants* are no longer recorded per technique.
  - **ADR-14's derived-authorization-set consequence is superseded with ADR-10.** ADR-14's migration-ledger decision (document-in-SQLite, `PRAGMA user_version`) stands; its "authorizable-technique set derived from `AcquisitionPolicy`'s boolean fields" consequence dies with the per-technique model.
  - Secrets rules remain the one non-overridable boundary.
  - Future agents MUST NOT reintroduce per-technique consent tiers or an authorization-ceremony step without a superseding ADR.

---
## ADR-16: Assess-and-exploit boundary lifted — ban removed, nothing built yet (2026-08-02)
- **Status:** accepted — supersedes the assess-not-exploit bound of ADR-12; the bounded-business-intelligence bound of ADR-12 **remains standing** (user confirmed 2026-08-02: "only the exploit bound")
- **Context:** The user directed (2026-08-02): remove the security constraints that feel restrictive; the project should stay flexible. Asked directly whether the tool should be able to "test exploit" when consented, the user confirmed: lift the ban, but **build nothing yet** — this session removes the prohibition only. Asked separately whether the ADR-12 bounded-business-intelligence bound should also be lifted, the user said **no** — only the exploit bound.
- **Decision:** The standing "assess, never exploit" boundary is **lifted**. Nothing in the project's rules any longer forbids going beyond detection (performing a bypass, firing a payload, authenticating to a reachable admin panel) — provided the single authorization (ADR-15) is set and the operator is responsible for the target. **No exploit capability is added in this session** — the tool's behavior is unchanged until future work deliberately adds exploit actions.
- **Consequences:**
  - The README promise "it does not bypass authentication" becomes a description of *current* behavior, not a binding constraint; update it if/when exploit actions land.
  - Future agents may design exploit actions without a superseding ADR, but each exploit action must still run only under the single authorization (ADR-15), carry its own risk assessment, and be recorded (own ADR or backlog item) before implementation.
  - This ADR is the "explicit user direction" ADR-12 required before crossing the boundary.
  - **The bounded-business-intelligence bound of ADR-12 stays in force:** purpose-built organization-profiling collectors remain prohibited, and `RESELLS_BANDWIDTH` stays capped at low (ADR-3) — unless a future superseding ADR lifts it.

---
## ADR-17: Disclosure schema relaxed — findings may be lightweight (2026-08-02)
- **Status:** accepted — supersedes the ADR-11 consequence that every finding carries the full disclosure schema (and the matching `user/preferences.md` bullet)
- **Context:** The user directed (2026-08-02): "Drop evidence schema" — the mandatory disclosure structure (Title, Affected asset, Evidence, Impact, Confidence, Recommended remediation, Verification status) felt restrictive.
- **Decision:** The disclosure schema becomes **optional in intent**. A finding may be a bare `check_slug` + `title` + `severity` + `confidence`; the full schema is one valid shape, not the required one. Evidence citation and confidence scores remain good practice — they are the product's differentiator — but they are no longer mandated per finding.
- **Consequences:**
  - **Code alignment is a separate backlog item:** `SecurityFinding`'s required fields (`impact`, `remediation`, `verification_status`) become optional; `run_checks` and the Markdown/SARIF renderers tolerate missing fields.
  - The `user/preferences.md` "disclosure must be evidence-backed" bullet is updated in place to match (current-state file, provenance refreshed).
  - Future agents MUST NOT re-mandate the full schema without a superseding ADR.
