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
