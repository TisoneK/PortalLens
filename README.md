# PortalLens

> Intelligence and security analysis for digital portals — captive Wi-Fi first.

PortalLens takes a portal URL (today: a captive Wi-Fi portal URL) and produces an **evidence-backed report** that distinguishes observed facts, inferences, and hypotheses, each carrying an explicit confidence score.

It is built for the situation where you've been redirected through a captive portal (e.g. `maz.wifi` → `captive.ispman.tech`) and want to know:

- What platform is this portal running? (MikroTik RouterOS? ISPMan? CoovaChilli?)
- Who operates the underlying Wi-Fi network?
- Is the redirect target a platform provider, a reseller, or the network operator itself?
- What can we say with confidence vs. what's speculation?

PortalLens never claims something as fact unless the evidence supports it. Hypotheses are explicitly labelled and capped at `low` confidence by convention.

## Status

Alpha — captive Wi-Fi passive analysis is implemented and tested against a real ISPMan URL pair. Active security assessment is gated behind explicit authorization and is the next planned surface.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

### Passive analysis (default — no network access)

```bash
portallens "http://maz.wifi/login?dst=http%3A%2F%2Fwww.msftconnecttest.com%2Fredirect"
```

### Passive analysis with multiple URLs

If you captured both the local captive hostname AND the external portal URL the redirect landed on, pass both — the relationship analyzer uses the pair to infer `REDIRECTS_TO`, `USES_PLATFORM`, `OPERATES_NETWORK`, etc.

```bash
portallens \
    "http://maz.wifi/login?dst=..." \
    "https://captive.ispman.tech/hotspots/.../select?..."
```

### Library use

```python
from portallens.portal import AnalysisContext
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.reporting import render_markdown

portal = CaptiveWifiPortal()
report = portal.analyze(AnalysisContext(urls=[
    "http://maz.wifi/login?dst=...",
    "https://captive.ispman.tech/hotspots/.../select?...",
]))
print(render_markdown(report))
```

### Active analysis (requires explicit authorization)

Active techniques — HTTP fetching, DNS resolution, port scanning — are gated behind an `AcquisitionPolicy` and a CLI authorization flag. The default policy is **passive**.

```bash
portallens --fetch-urls --i-have-authorization "https://example.com/login"
```

**Do not run active analysis against networks you do not own or have explicit written permission to assess.**

## Architecture

PortalLens is built around one abstraction: the `Portal`. Every portal type (captive Wi-Fi, web auth, payment, ISP) is a `Portal` subclass registered against a `PortalType`. The CLI dispatches a URL to the right analyzer via the registry.

```
PortalLens
├── src/portallens/
│   ├── portal.py              # Portal base + PortalReport + AcquisitionPolicy
│   ├── confidence.py          # 0–100 confidence + label rubric
│   ├── evidence.py            # Evidence + Observation (fact / inference / hypothesis)
│   ├── registry.py            # @register_portal decorator
│   ├── acquisition/           # URL parsing (passive) + HTTP fetch (active, gated)
│   ├── reporting/             # Markdown renderer (canonical output)
│   ├── plugins/
│   │   └── captive_wifi/      # First plugin — fingerprinting + relationship inference
│   └── cli.py                 # `portallens` CLI
├── tests/                     # Unit + end-to-end tests with real ISPMan URL fixture
└── pyproject.toml
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

## Confidence model

Every non-fact statement in a PortalLens report carries an integer confidence in `[0, 100]` and a derived label:

| Range | Label | Meaning |
|---|---|---|
| 0–19 | `very_low` | Speculative — no direct evidence; could easily be wrong. |
| 20–39 | `low` | Weak signal — one indirect indicator; treat as a hypothesis. |
| 40–59 | `medium` | Plausible — multiple indirect indicators or one strong one. |
| 60–79 | `high` | Likely — strong, specific evidence; alternatives less probable. |
| 80–100 | `very_high` | Established — direct, unambiguous evidence. |

Multiple independent evidence signals are combined via a noisy-OR rule (`score([w1, w2, …])`) so two medium signals can lift an inference into `high`, but a single speculative signal never escapes `low`.

## What PortalLens does NOT do

- **It does not bypass authentication.** PortalLens analyzes portal URLs passively. It never submits credentials, never tries to skip the captive-portal handshake, and never attempts to obtain free internet access.
- **It does not actively probe networks without authorization.** Every active technique (HTTP fetch, DNS lookup, port scan, TLS probe) requires an explicit `AcquisitionPolicy` flag in the library, or `--i-have-authorization` on the CLI. **The caller is responsible for ensuring they have authorization for the target.**
- **It does not guess.** If the evidence can't distinguish a reseller from an operator using a 3rd-party platform, PortalLens says so — explicitly, as a hypothesis with `low` confidence, and lists what evidence would resolve the question.

## Responsible disclosure

PortalLens is intended for:

- **Operators** assessing their own captive portals before deployment.
- **Security researchers** with explicit, written authorization to assess a target.
- **Network auditors** producing evidence-backed reports for responsible disclosure.

The output is structured to support responsible disclosure: every finding cites the evidence it rests on, every inference carries a confidence score, and every gap in the evidence is surfaced as an open question rather than papered over.

## License

MIT — see [`LICENSE`](LICENSE).

## Agent memory

This repository uses the [`.context/`](https://github.com/TisoneK/.context) protocol for persistent AI agent memory. Every session reads `.context/kickoff.md` first and follows the protocol vendored at `.context/core/`. See [`AGENTS.md`](AGENTS.md) for the short-form agent instructions.
