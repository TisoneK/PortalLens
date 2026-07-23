# Backlog (append-only)

Open items for future sessions. Append at the bottom; never delete or
reorder. When an item is done, check it off and note the session/commit —
don't remove the line.

---
- [ ] **NetAudit module** (added 2026-07-23 by Super Z / Session 1) — active security-assessment surface, gated behind `AcquisitionPolicy` flags. The `acquisition/fetcher.py` is in place; what's missing is the security-audit analyzer that uses it. Pick a small, well-scoped first audit (e.g. "is the MikroTik admin interface exposed on the customer network?") and implement it as a separate `Portal` subclass or as a method on `CaptiveWifiPortal` that runs only when `AcquisitionPolicy.fetch_urls=True`. The user explicitly stated active analysis requires authorization — never run this against networks you don't own.

---
- [ ] **DisclosureDesk module** (added 2026-07-23 by Super Z / Session 1) — responsible-disclosure report generation + tracking. Extends `reporting/` with SARIF output and a disclosure-state machine (draft → submitted → acknowledged → fixed → published). The user's preference (in `user/preferences.md`) is that every finding states Title, Affected asset, Evidence, Impact, Confidence, Recommended remediation, and Verification status — DisclosureDesk should enforce that schema.

---
- [ ] **CoovaChilli fixture + tests** (added 2026-07-23 by Super Z / Session 1) — the test suite has a CoovaChilli fingerprint detector (`src/portallens/plugins/captive_wifi/fingerprints.py::_detect_coorvachilli`) but no CoovaChilli URL fixture in `tests/data/`. Find a real CoovaChilli captive portal URL (or construct one from the documented signature: `challenge` parameter, or `userurl` + `uamip` together) and add a `TestCoovaChilli` class to `tests/test_fingerprints.py` + `tests/test_url_parser.py`.

---
- [ ] **HTML fingerprinting** (added 2026-07-23 by Super Z / Session 1) — the `EvidenceType` enum already includes `HTML_ELEMENT` and `JS_BUNDLE`, but the analyzer doesn't yet capture HTML evidence. Wire up the `--html-file URL:PATH` CLI flag (the option exists in `cli.py` but the path→URL mapping is incomplete) and add an HTML fingerprint detector that recognizes ISPMan / MikroTik / CoovaChilli by their portal HTML signatures. This is the natural next step beyond URL-only passive analysis — still passive (user supplies the HTML), but much higher-fidelity fingerprints.

---
- [ ] **DNS resolution** (added 2026-07-23 by Super Z / Session 1) — `AcquisitionPolicy.resolve_dns` is defined but no code uses it. Add a `portallens/acquisition/dns.py` module that resolves a hostname (A / AAAA / CNAME / TXT) and emits `EvidenceType.DNS_RECORD` evidence. Use stdlib `socket` for A/AAAA, or `dnspython` for full record-type support. This is the lowest-risk active technique — DNS queries are not "probing" in any meaningful sense — but still requires explicit opt-in via the policy flag.

---
- [ ] **IP/ASN lookup** (added 2026-07-23 by Super Z / Session 1) — required to close the "who is the upstream ISP?" open question that every captive-portal report currently surfaces. Integrate a free IP/ASN API (e.g. RIPEstat `https://stat.ripe.net/data/whois/data.json`) behind `AcquisitionPolicy`. Emits `EvidenceType.IP_ASN` evidence. Once this lands, the analyzer can start emitting `UPSTREAM_OF` relationships with real confidence instead of leaving the question open.

---
- [ ] **SARIF output** (added 2026-07-23 by Super Z / Session 1) — for security-audit findings, SARIF is the industry-standard interchange format (GitHub code scanning, Azure DevOps, etc.). Add `render_sarif()` alongside `render_markdown()` in `reporting/`. SARIF is only meaningful once the NetAudit module produces actual security findings — passive analysis doesn't have findings to report in SARIF.

---
- [ ] **`web_auth` plugin** (added 2026-07-23 by Super Z / Session 1) — the `PortalType.WEB_AUTH` enum value is reserved but no plugin is registered against it. A natural second plugin: SSO / OAuth / OIDC login flows. The fingerprint + relationship model adapts directly — the URL signatures and platform detectors change (e.g. `client_id`, `redirect_uri`, `state`, `code_challenge` parameters for OAuth/OIDC), but the `Portal` abstraction doesn't. Implementing this would validate the plugin architecture's claim that new portal types slot in without an architectural rewrite.

---
- [ ] **Validate the three documented-only signatures** (added 2026-07-23 by Claude Code / Session 2) — `COOVACHILLI`, `UNIFI`, and `MERAKI` in `src/portallens/plugins/captive_wifi/signatures.py` carry `Provenance.DOCUMENTED`: their rules were transcribed from vendor documentation and have never been matched against a real captured URL. Each needs a capture added to `tests/data/`, a test class in `tests/test_signatures.py`, and then a flip to `Provenance.VALIDATED`. **This supersedes the session-1 "CoovaChilli fixture + tests" item by widening it to all three.** Until validated, every report those signatures fire on carries a note and an open question saying the match is provisional — do not remove that mechanism to make output look cleaner; it is the honesty guarantee the confidence model rests on (see ADR-5).

---
- [ ] **Decide where the signature provenance ledger lives** (added 2026-07-23 by Claude Code / Session 2) — the user's standing preference (`user/preferences.md`) is that fingerprint/signature knowledge accumulate in `.context/memory/` rather than being rediscovered per session. The runtime registry rightly lives in `src/` (it is executable data), but the *provenance* of each signature — which vendor doc or capture it came from, who validated it, against what URL, on what date — has no home yet and is exactly the kind of knowledge the preference is about. Decide whether `memory/` should carry that ledger, and if so seed it from the five signatures currently in the registry.

---
- [ ] **HTML fingerprinting is now cheaper — revisit the existing item** (added 2026-07-23 by Claude Code / Session 2) — the session-1 "HTML fingerprinting" backlog item predates the signature registry. It no longer needs a per-vendor HTML detector: add an `html_markers` field to `PortalSignature` plus one detector pass over the registry, and every registered provider gains HTML detection at once. Do this rather than writing `_detect_ispman_html()` and friends — that is precisely the pattern session 2 removed.

---
- [ ] **Structured `OpenQuestion`** (added 2026-07-23 by Claude Code / Session 3, per ADR-9) — replace `PortalReport.open_questions: list[str]` with an `OpenQuestion` model: `subject`, optional edge `kind` (`RelationshipKind`), `question` text, and `resolves_with: list[str]` (analysis-step slugs). Migrate `analyzer._open_questions()` to emit these; update `reporting/` to render `resolves_with` as a field. **This is the well-scoped first slice of the whole TUI/investigation direction** — small, improves the Markdown today, and it's the anchor the relationship graph and the "next investigation" menu both need. Build this before any TUI or persistence code.

---
- [x] **`Investigation` core + SQLite persistence** — DONE 2026-07-23 (Claude Code / Session 5, commits d82c5a1 + 58d9478; concrete design in ADR-14; 33 tests; verified end-to-end across 4 processes). *(Original spec below.)* (added 2026-07-23 by Claude Code / Session 3, per ADR-8, ADR-10) — introduce `Investigation` as a persisted core aggregate (target, evidence/observations/relationships, authorization record, audit log). SQLite, migrations from day one. `analyze()` becomes "step zero"; steps append to a growing report. Authorization recorded per-technique, timestamped, as part of the audit trail (ADR-10). Shared foundation for the TUI **and** the backlogged DisclosureDesk state machine — build it as a core concern, not a TUI feature.

---
- [ ] **`AnalysisStep` registry + first two steps (DNS, IP/ASN)** (added 2026-07-23 by Claude Code / Session 3, per ADR-9) — a registry parallel to the signature registry: each step declares `slug`, `label`, required `AcquisitionPolicy` technique (`None`=passive), produced `EvidenceType`s, and answerable question `kind`s. The "next investigation" list is computed by matching open questions to steps that answer them. Ship DNS and IP/ASN as the first two real steps (both already backlogged separately, both passive-ish/low-risk, and together they close the upstream-ISP question every report ends on). This is where the "pull the thread" loop first works — headless, before any TUI.

---
- [x] **Investigation-console TUI (Textual, responsive)** (added 2026-07-23 by Claude Code / Session 3, per ADR-7; done 2026-07-23 by Super Z / Session 4, commit e06107a) — a pure presentation layer over the engine: renders `Investigation`/`PortalReport`, issues commands, contains no analysis logic. Behind an optional extra (`portallens[tui]`). **Must be responsive from ~40 columns (Termux, portrait) to wide desktop** — panels reflow/stack; the relationship graph degrades to an indented/linear form on narrow terminals; severity/status never colour-only. Build the hypothesis/evidence panel first (it's the product), then the relationship graph (the one screen that genuinely beats Markdown, because it makes the unknown-upstream gap structural). Preserve the `plugins/<type>/` vertical slice — `tui/` is a sibling layer, not a reorg.
  - **Done in session 4.** `src/portallens/tui/` (theme, widgets, app, __init__ shim). `PortalLensApp` renders a `PortalReport` the engine already produced. `RelationshipView` swaps at `WIDE_THRESHOLD=100` via `on_resize`. CLI is `_DefaultAnalyzeGroup` with `analyze` + `tui` subcommands; `portallens <urls>` falls back to `analyze`. 22 new tests (102 total). See `reviews/2026-07-23-review-3.md`. The TUI is stateless today — it renders one report and quits. The `Investigation` aggregate (ADR-8) is what gives it drill-down, history, and incremental steps; that's the next layer.

---
- [ ] **`SecurityCheck` registry** (added 2026-07-23 by Claude Code / Session 3, per ADR-11, ADR-12) — security checks as data, keyed on required evidence (not on vendor), parallel to the signature registry. Each finding carries the disclosure schema + confidence bands; `DOCUMENTED`-provenance checks are marked provisional. Assess-only, never exploit (ADR-12). This is the backbone for the backlogged NetAudit module — NetAudit becomes "run the SecurityCheck registry under active policy" rather than a pile of per-check functions.

---
- [ ] **Certificate Transparency log mining (Tier-1 OSINT)** (added 2026-07-23 by Claude Code / Session 3, per ADR-11, ADR-13) — given a portal hostname, query CT logs (crt.sh / Censys) for every certificate on that infrastructure → surfaces every *other* operator on the same hosted platform. Zero contact with the target; gated behind the new `use_osint_apis` tier (ADR-13), not `fetch_urls`. Feeds relationship inference directly (shared cert infra = a real `SAME_OPERATOR`/`USES_PLATFORM` signal with weight, not a URL guess). **One of the two highest-value/lowest-risk security additions** — build early.

---
- [ ] **Client-fingerprinting privacy finding (Tier-3)** (added 2026-07-23 by Claude Code / Session 3, per ADR-11) — the analyzer already parses `canvasFingerprint`, `webgl`, `userAgent`, screen dimensions, timezone, `cookie` from captured portal URLs. Emit a security/privacy finding when a portal collects device-fingerprinting parameters **before authentication**: "this portal fingerprints your device pre-login; here is the evidence." Purely defensive, protects the portal's *users* (not just its operator), needs **no new collection** — it reports on data already held. Distinctive to PortalLens precisely because it already collects these as a side effect of platform fingerprinting. The other of the two build-early security items.

---
- [ ] **Structured `OpenQuestion` (ADR-9) — now the clear next build** (re-affirmed 2026-07-23 by Claude Code / Session 5) — with persistence (ADR-8) and the TUI (ADR-7) both in place, the missing piece both want is structured open questions: replace `PortalReport.open_questions: list[str]` with an `OpenQuestion` model (`subject`, optional edge `kind`, `question`, `resolves_with: list[step-slug]`). The investigation store already serializes it for free (pydantic JSON) — no store change needed. This unblocks the "next investigation" computed queue and gives the TUI's open-questions panel real structure. See the ADR-9 backlog entry above for full detail.

---
- [ ] **First analysis step (DNS) against a persisted investigation** (added 2026-07-23 by Claude Code / Session 5, per ADR-9 + ADR-10) — this is where an investigation stops being a saved report and becomes a growing one. The enforcement seam is already built and tested: a step checks `investigation.is_authorized("resolve_dns")` before running, and appends its `DNS_RECORD` evidence + an audit entry to the persisted investigation. Needs: the `AnalysisStep` registry (ADR-9 item), a `resolve_dns` step, and a CLI verb (e.g. `portallens step <id> resolve_dns`) that loads → checks authorization → runs → saves.
