# PortalLens

> Intelligence and security analysis for digital portals — captive Wi-Fi first.

PortalLens takes a portal URL (today: a captive Wi-Fi portal URL) and produces an **evidence-backed report** that distinguishes observed facts, inferences, and hypotheses, each carrying an explicit confidence score.

It is built for the situation where you've been redirected through a captive portal (e.g. `maz.wifi` → `captive.ispman.tech`) and want to know:

- What platform is this portal running? (MikroTik RouterOS? CoovaChilli? UniFi? ISPMan? Meraki?)
- Who operates the underlying Wi-Fi network?
- Is the redirect target a platform provider, a reseller, or the network operator itself?
- What can we say with confidence vs. what's speculation?

PortalLens never claims something as fact unless the evidence supports it. Hypotheses are explicitly labelled and capped at `low` confidence by convention.

## Status

Alpha — captive Wi-Fi passive analysis and bounded bypass detection are implemented and tested against a real ISPMan URL pair. The MikroTik and ISPMan signatures are validated against that capture; the CoovaChilli, UniFi, and Meraki signatures come from vendor documentation and have not yet been checked against a captured URL, which the report says wherever one of them fires. Active security assessment is gated behind explicit authorization.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # library + CLI + dev tools (includes the TUI extra)
# or, for just the library + CLI:
pip install -e .
# or, for the TUI only:
pip install -e ".[tui]"
```

The TUI is an optional extra (ADR-7): `pip install -e ".[tui]"` pulls Textual.
Without it, `portallens analyze <urls>` works but `portallens tui <urls>`
prints a clear install hint. A script doing
`from portallens import PortalReport` never pulls Textual — the TUI is
lazy-imported inside the `tui` subcommand only.

## Usage

The full, step-by-step tutorial lives in **[`docs/TUTORIAL.md`](docs/TUTORIAL.md)** — every command with all its options, the report walkthrough, saved investigations, the library API, the authorized bypass probes, and troubleshooting. This section is the quick tour.

### Quick start

```bash
# Passive analysis (default — no network access)
portallens "http://maz.wifi/login?dst=..."

# Two URLs: the local captive host + the external portal it redirected to.
# The pair lets the relationship analyzer infer REDIRECTS_TO, USES_PLATFORM,
# OPERATES_NETWORK, etc.
portallens \
    "http://maz.wifi/login?dst=..." \
    "https://captive.ispman.tech/hotspots/.../select?..."

# Same analysis, opened in the LIVE investigation console — streamed
# activity feed + keyboard controls (1-9 run next steps, p=probe,
# m=monitor, s=save, e=export; needs the [tui] extra)
portallens tui "http://maz.wifi/login?dst=..."

# Persist, list, re-render, and extend an investigation
portallens investigate "http://maz.wifi/login?dst=..."
portallens investigations
portallens show <id>
portallens step <id> resolve_dns
```

### Command surface

| Command | What it does |
|---|---|
| `portallens <urls>...` | Shortcut for `analyze` — passive analysis, Markdown report on stdout |
| `portallens analyze <urls>...` | Explicit analysis; add `--format sarif`, `-o <file>`, `--notes` |
| `portallens tui <urls>...` | Live investigation console — report panels, streaming activity feed, and controls to run next steps / probes / save / export (`--auto`, `--monitor`, `--monitor-interval`) |
| `portallens investigate <urls>...` | Analyze and save as a persisted investigation |
| `portallens investigations` | List saved investigations, newest first |
| `portallens show <id> [--audit]` | Re-render a saved report (or its audit trail) |
| `portallens step <id> <slug>` | Run one analysis step against a saved investigation (`resolve_dns`, `ip_asn_lookup`) |

### Passive by default — active only with `--authorized`

Analysis never touches the network unless you say so. **One flag —
`--authorized` — unlocks every active technique** (HTTP fetching, DNS
resolution, port scanning, OSINT, bypass probes; ADR-15):

```bash
portallens --authorized "https://example.com/login"
```

You are responsible for targets you authorize. **Do not run active
analysis against networks you do not own or have explicit written
permission to assess.**

### Library use

```python
from portallens.portal import AnalysisContext
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.reporting import render_markdown

report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[
    "http://maz.wifi/login?dst=...",
    "https://captive.ispman.tech/hotspots/.../select?...",
]))
print(render_markdown(report))
```

### Learn more

The **[full tutorial → `docs/TUTORIAL.md`](docs/TUTORIAL.md)** covers
each command with its options, how to read a report (confidence model,
facts vs. inferences vs. hypotheses), the TUI, saved investigations and
analysis steps, the five authorized bypass probes (`connect_test`,
`dns_tunnel_test`, `click_through_test`, `port_scan_test`,
`parameter_tampering_test`), SARIF output, and troubleshooting.

## Architecture

PortalLens is built around one abstraction: the `Portal`. Every portal type (captive Wi-Fi, web auth, payment, ISP) is a `Portal` subclass registered against a `PortalType`. The CLI dispatches a URL to the right analyzer via the registry.

Within the captive Wi-Fi analyzer, the platforms themselves are data. Everything PortalLens knows about a provider — how to recognize it, what each signal is worth, and whether the rule has ever been checked against a real captured URL — lives in one registry, so adding a provider is a registry entry rather than a code change.

```
PortalLens
├── src/portallens/
│   ├── portal.py              # Portal base + PortalReport + AcquisitionPolicy
│   ├── confidence.py          # 0–100 confidence + label rubric
│   ├── evidence.py            # Evidence + Observation (fact / inference / hypothesis)
│   ├── registry.py            # @register_portal decorator
│   ├── acquisition/           # URL parsing (passive) + HTTP fetch (active, gated)
│   ├── security/              # Security checks, NetAudit, bounded bypass probes
│   ├── reporting/             # Markdown renderer (canonical output)
│   ├── investigation/         # Investigation aggregate + SQLite store (persistence)
│   ├── tui/                   # investigation-console TUI (optional [tui] extra)
│   ├── plugins/
│   │   └── captive_wifi/      # First plugin — fingerprinting + relationship inference
│   │       └── signatures.py  # the provider registry — the only file that names a vendor
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
- **It does not actively probe networks without authorization.** Every active technique (HTTP fetch, DNS lookup, port scan, OSINT lookup, or bypass probe) is unlocked by `AcquisitionPolicy(authorized=True)` in the library, or `--authorized` on the CLI (ADR-15). **The caller is responsible for ensuring they have authorization for the target.**
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
