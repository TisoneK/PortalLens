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
