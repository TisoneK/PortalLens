# Architecture

## Goals

1. **Passive by default.** PortalLens works purely from URLs and user-supplied payloads. Active probing (HTTP fetches, DNS lookups, port scans) requires explicit opt-in AND authorization.
2. **Evidence-backed.** Every inference cites the evidence it rests on. Every gap is surfaced as an open question. Hypotheses are labelled as such, with confidence capped at `low`.
3. **Plugin-based.** The core abstraction is `Portal`. Captive Wi-Fi is the first plugin; web auth, payment, ISP portals slot in without an architectural rewrite.
4. **Calibrated confidence.** A 60% claim means "likely, with specific evidence" — not "the model felt 60% confident." The rubric is documented; the score combination rule (noisy-OR) is documented; both are tested.

## Core abstractions

### `Portal` (abstract base)

Every portal type implements:

```python
class Portal(ABC):
    portal_type: PortalType

    @abstractmethod
    def analyze(self, context: AnalysisContext) -> PortalReport: ...
```

The `AnalysisContext` carries URLs, optional HTML/HAR payloads, an `AcquisitionPolicy`, and free-text user notes. The `PortalReport` is the immutable output — evidence, observations (facts/inferences/hypotheses), fingerprints, relationships, and open questions.

### `Evidence` vs. `Observation`

PortalLens separates three kinds of statements in its reports:

- **Evidence** — raw, sourced observations: a URL parameter was present, an HTTP header returned a specific value, a DNS record resolved. Immutable records with stable ids.
- **Facts** — restatements of one or more `Evidence` records. Confidence is always 100%.
- **Inferences** — conclusions drawn from evidence, with a confidence score and the evidence ids they rest on.
- **Hypotheses** — speculative explanations offered when evidence is thin. Confidence is capped at 39 (`low`) by convention. Always flagged for verification.

A report reader can always trace "why does this say 72%?" back to the raw inputs.

### `Confidence`

Integer in `[0, 100]` plus a derived label (`very_low` / `low` / `medium` / `high` / `very_high`). The label rubric is documented in `src/portallens/confidence.py` and surfaced in every report.

Multiple evidence weights are combined via `score([w1, w2, …])` using a noisy-OR rule:

```
combined = 1 - prod(1 - w_i / 100)
```

This means two independent medium signals reinforce each other (40 + 40 → 64), but a single speculative signal never escapes `low` (10 + 10 + 10 → 27).

### `AcquisitionPolicy`

A dataclass with explicit flags for every active technique:

```python
@dataclass
class AcquisitionPolicy:
    fetch_urls: bool = False
    follow_redirects: bool = False
    resolve_dns: bool = False
    probe_tls: bool = False
    port_scan: bool = False
```

The default policy is passive. Active functions in `portallens.acquisition.fetcher` call `assert_policy(policy, "fetch_urls")` before doing anything — a typo can't accidentally turn a passive scan into an active one.

## Plugin architecture

```
Portal (abstract)
└── CaptiveWifiPortal (registered against PortalType.CAPTIVE_WIFI)
    ├── signatures.py     # the provider registry — every platform PortalLens knows
    ├── url_parser.py     # passive URL parsing — runs the registry against a URL
    ├── fingerprints.py   # scores each matched signature into a confidence
    ├── relationship.py   # REDIRECTS_TO / USES_PLATFORM / OPERATES_NETWORK / RESELLS_BANDWIDTH
    └── analyzer.py       # ties it together, builds the PortalReport
```

Only `signatures.py` names a vendor. The three modules below it iterate the
registry, so teaching the analyzer a new provider is a registry entry, not a
code change.

Future plugins (`web_auth`, `payment`, `isp`) register themselves the same way on import:

```python
@register_portal(PortalType.WEB_AUTH)
class WebAuthPortal(Portal):
    portal_type = PortalType.WEB_AUTH
    def analyze(self, context): ...
```

The CLI dispatches via the registry: `get_portal_class(PortalType.WEB_AUTH)`.

## captive_wifi analyzer — design notes

### URL parsing is passive and signature-based

The analyzer never fetches a URL to fingerprint it. It works purely from `urllib.parse`. Each entry in the registry is a `PortalSignature`: a set of rules that decide whether it fires, and the weights each matched signal contributes.

A rule can require query parameters (all of them, or any of one set, or *n* of the platform's known variables), a host suffix, and a path prefix/suffix. A signature fires if any of its rules matches:

- **MikroTik** (gateway): `link-login` + `link-orig` together, or ≥4 of its documented hotspot variables, or `dst` on a `/login` path.
- **CoovaChilli** (gateway): `challenge`, or `userurl` + `uamip` together.
- **UniFi** (gateway): the `/guest/s/<site>/` controller path plus one of `id` / `ap` / `ssid`.
- **ISPMan** (hosted platform): host suffix `ispman.tech` + path prefix `/hotspots/` + path suffix `/select`.
- **Meraki** (hosted platform): host suffix `network-auth.com` + path prefix `/splash/`.

Host suffixes match on label boundaries, so `evilispman.tech` is not ISPMan.

### Two layers: gateways and hosted platforms

The registry distinguishes the software running on the operator's own hardware (**gateway** — MikroTik, CoovaChilli, UniFi; identified by the query variables it emits) from the service hosting the portal on the operator's behalf (**hosted platform** — ISPMan, Meraki; identified by its own host and path).

The distinction is what makes relationship inference provider-agnostic. A redirect landing on *any* hosted-platform host supports `USES_PLATFORM` and `AUTHENTICATES_FOR`, and a host owned by a hosted platform is never reported as the network operator. Neither rule names a vendor.

A URL routinely matches both layers: the ISPMan URL captured from the wild carries the MikroTik signature too, because MikroTik's redirect forwards its full parameter set to the external portal.

### Fingerprints are independent and additive

Each matched signature is scored independently and produces its own `FingerprintMatch` with its own confidence. A single URL can produce multiple matches — that's a feature, not a bug. The report surfaces all of them so the reader can see the full picture.

### Signatures carry their provenance

A rule transcribed from vendor documentation is not as trustworthy as one checked against a real captured URL, and a calibrated report must not present them identically. Every signature records which it is. A signature that has never matched a URL in this project's fixtures says so in its fingerprint note and adds an open question inviting the reader to discount the match.

### Relationship inference is asymmetric

The key insight (from the PortalLens design conversation): a single observed redirect (`maz.wifi` → `captive.ispman.tech`) supports some inferences very strongly but NOT others. The table below uses the ISPMan fixture, but the rules behind it read the registry — substitute any hosted platform and the reasoning is identical.

| Inference | Confidence | Why |
|---|---|---|
| `maz.wifi` redirects to `captive.ispman.tech` | high (≥70) | Direct redirect evidence. |
| `maz.wifi` uses ISPMan as platform | high (≥60) | Redirect target + ISPMan host/path fingerprint. |
| ISPMan authenticates for `maz.wifi` | high (≥75) | By construction — the redirect target IS the auth portal. |
| `maz.wifi` operates the network | medium-high (~70) | Local-only TLD + serves captive portal = local operator. |
| `maz.wifi` resells upstream bandwidth | low (~35) | URL alone cannot distinguish reseller from operator-using-platform. |

The `RESELLS_BANDWIDTH` relationship is deliberately capped at `low` — without pricing evidence, package menus, or upstream ISP identification (ASN/IP), we cannot distinguish the two scenarios. The report surfaces this explicitly as a hypothesis and lists what evidence would resolve it.

### Open questions are mandatory

The analyzer populates `PortalReport.open_questions` for anything it couldn't close with the supplied evidence. These are always present (without authorized active assessment):

1. Who is the legal entity behind the local operator hostname?
2. Who is the upstream Internet bandwidth provider?
3. Is the administrative interface of each detected gateway exposed to the customer network?
4. Does each fingerprint whose signature has never been validated in the field actually hold?

These are the prompts for follow-up — either with more user input (HTML captures, DNS records) or an explicitly authorized active assessment.

## Future surfaces

The PortalLens design conversation identified three components:

- **PortalLens** — passive portal intelligence. *(Implemented here.)*
- **NetAudit** — authorized active security assessment. *(Planned — separate `audit` module behind `AcquisitionPolicy` flags.)*
- **DisclosureDesk** — responsible disclosure report generation + tracking. *(Planned — extends `reporting/` with SARIF + disclosure-tracking output.)*

The `Portal` abstraction is broad enough that NetAudit can be implemented as another plugin (`PortalType.CAPTIVE_WIFI` analyzer with active policy enabled), rather than a separate product. DisclosureDesk is a reporting concern, not an analysis concern — it lives alongside `render_markdown` in `reporting/`.

## Why the design is the way it is

### Why noisy-OR for confidence combination?

Three independent weak signals should reinforce each other, but no number of weak signals should reach certainty. Noisy-OR gives us that: `1 - prod(1 - w/100)`.

Alternative considered: max-combination (`max([w1, w2])`). Rejected — it doesn't reinforce. Two independent 40% signals would stay at 40%, when they should plausibly lift to ~60%.

Alternative considered: weighted average. Rejected — it dilutes. A 80% signal combined with a 10% signal would drop to 45%, when the 80% signal is the one that matters.

### Why cap hypotheses at `low`?

A hypothesis is "we don't have enough evidence to call this an inference." If we did, it would be an inference. The cap forces the report to be honest about what's speculation vs. what's evidence-backed — the reader knows to take `low` claims as prompts for verification, not as findings.

### Why is the analyzer passive by default?

Two reasons:

1. **Legal.** Active probing of networks you don't own is unauthorized scanning in most jurisdictions. PortalLens must not make it easy to do that by accident.
2. **Calibration.** A passive analyzer's confidence scores are interpretable: "this URL signature is X% likely to be MikroTik." An active analyzer that fetches a URL adds the confound of "the URL might respond differently to a bot vs. a browser" — the calibration gets murky.

Passive is the right default. Active is opt-in, per-technique, per-session, with an explicit authorization flag.
