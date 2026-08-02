# PortalLens Tutorial

This is the full, step-by-step guide to using PortalLens. The README
carries the quick-start summary; everything below — every command with
its options, the report format, the library API, saved investigations,
and the authorized bypass probes — lives here.

PortalLens takes a portal URL (today: a captive Wi-Fi portal URL, and
ideally the pair formed by the local captive hostname plus the external
portal it redirected to) and produces an **evidence-backed report** that
separates observed facts from inferences and hypotheses, each carrying an
explicit confidence score. It never claims something as fact unless the
evidence supports it.

- [1. Installation](#1-installation)
- [2. Quick start](#2-quick-start)
- [3. Analyze: fingerprinting a portal URL](#3-analyze-fingerprinting-a-portal-url)
- [4. Reading the report](#4-reading-the-report)
- [5. The interactive console (`tui`)](#5-the-interactive-console-tui)
- [6. Saved investigations and analysis steps](#6-saved-investigations-and-analysis-steps)
- [7. Active analysis: the `--authorized` flag](#7-active-analysis-the---authorized-flag)
- [8. Bypass detection probes (library)](#8-bypass-detection-probes-library)
- [9. Using PortalLens as a library](#9-using-portallens-as-a-library)
- [10. Troubleshooting](#10-troubleshooting)
- [11. Responsible use](#11-responsible-use)

---

## 1. Installation

PortalLens is a Python package. It requires **Python 3.10+**.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # library + CLI + dev tools (includes the TUI extra)
# or, for just the library + CLI:
pip install -e .
# or, for the TUI only:
pip install -e ".[tui]"
```

The three extras in one table:

| Install command | What you get |
|---|---|
| `pip install -e .` | Library + CLI (`portallens analyze` and friends) |
| `pip install -e ".[tui]"` | Adds the interactive investigation-console TUI (Textual) |
| `pip install -e ".[dev]"` | Everything above plus test/lint/typecheck tooling |

The TUI is an optional extra. Without it, `portallens analyze <urls>`
works but `portallens tui <urls>` prints a clear install hint. A script
doing `from portallens import PortalReport` never pulls Textual — the TUI
is lazy-imported inside the `tui` subcommand only.

Verify the install:

```bash
portallens --version
```

> **Windows note:** activate with `.venv\Scripts\activate` and use
> `.venv\Scripts\python` / `.venv\Scripts\portallens` instead of the
> bare names.

---

## 2. Quick start

```bash
# Passive analysis (default — no network access)
portallens "http://maz.wifi/login?dst=http%3A%2F%2Fwww.msftconnecttest.com%2Fredirect"

# Same analysis in the interactive console
portallens tui "http://maz.wifi/login?dst=..."

# Analyze, save, and inspect later
portallens investigate "http://maz.wifi/login?dst=..."
portallens investigations
portallens show <id>
```

Every command below is passive by default — nothing touches the network
unless you pass `--authorized` (see [section 7](#7-active-analysis-the---authorized-flag)).

---

## 3. Analyze: fingerprinting a portal URL

### One URL

```bash
portallens "http://maz.wifi/login?dst=http%3A%2F%2Fwww.msftconnecttest.com%2Fredirect"
```

This runs the captive-wifi analyzer: it parses the URL for platform
signatures (MikroTik RouterOS, CoovaChilli, UniFi, ISPMan, Meraki),
collects evidence, infers relationships, and prints a Markdown report.

`analyze` is also an explicit subcommand; passing URLs directly routes to
it, so both of these are equivalent:

```bash
portallens analyze "http://maz.wifi/login?dst=..."     # explicit
portallens "http://maz.wifi/login?dst=..."             # default-subcommand fallback
```

### Two URLs: the local host + the redirect target

If you captured both the local captive hostname **and** the external
portal URL the redirect landed on, pass both. The relationship analyzer
uses the pair to infer `REDIRECTS_TO`, `USES_PLATFORM`,
`AUTHENTICATES_FOR`, `OPERATES_NETWORK`, and (as a low-confidence
hypothesis) `RESELLS_BANDWIDTH`:

```bash
portallens \
    "http://maz.wifi/login?dst=..." \
    "https://captive.ispman.tech/hotspots/.../select?..."
```

The pair is the recommended invocation: a single local URL fingerprints
the platform, but the redirect pair is what lets PortalLens say something
about *who operates the network behind the portal*.

### Options

```
portallens analyze [OPTIONS] URL [URL ...]

  --type TEXT       Portal type to analyze as.
                    [default: captive_wifi — the only plugin today]
  --authorized      Enable ALL active techniques (see section 7).
  --notes TEXT      Free-text notes to attach to the analysis (e.g.
                    "captured from Android Chrome").
  --format [markdown|sarif]
                    Output format. [default: markdown]
  -o, --output PATH Write the report to this path instead of stdout.
  --db PATH         Investigations database path (see section 6).
```

Examples:

```bash
# Write a Markdown report to a file
portallens analyze "http://maz.wifi/login?dst=..." -o report.md

# Machine-readable SARIF 2.1.0 output (consumed by GitHub code scanning, etc.)
portallens analyze --format sarif "http://maz.wifi/login?dst=..."

# Attach capture context to the report
portallens analyze --notes "captured from Android Chrome on the hotel wifi" \
    "http://maz.wifi/login?dst=..."
```

---

## 4. Reading the report

The Markdown report is the canonical output. It is organized so you can
tell **what was observed** from **what was inferred** from **what is
speculation**:

| Section | Contains |
|---|---|
| Fingerprints | Which platform(s) the URLs match, with confidence (e.g. ISPMan 80%, MikroTik 78%) |
| Relationships | `REDIRECTS_TO`, `USES_PLATFORM`, `OPERATES_NETWORK`, ... each citing its evidence |
| Evidence | The raw observations behind the findings, each typed as fact / inference / hypothesis |
| Security findings | Registered security checks that fired on the evidence (see ADR-11) |
| Open questions | What the analysis could not close, and the steps that would resolve each |

### Confidence model

Every non-fact statement carries an integer confidence in `[0, 100]` and
a derived label:

| Range | Label | Meaning |
|---|---|---|
| 0–19 | `very_low` | Speculative — no direct evidence; could easily be wrong. |
| 20–39 | `low` | Weak signal — one indirect indicator; treat as a hypothesis. |
| 40–59 | `medium` | Plausible — multiple indirect indicators or one strong one. |
| 60–79 | `high` | Likely — strong, specific evidence; alternatives less probable. |
| 80–100 | `very_high` | Established — direct, unambiguous evidence. |

Multiple independent signals combine via a noisy-OR rule, so two medium
signals can lift an inference into `high`, but a single speculative
signal never escapes `low`. Hypotheses are capped at `low` by convention:
if the evidence were strong enough to be an inference, PortalLens would
label it one.

Two things to look for in every report:

- **Provenance notes.** Signatures validated against a real captured URL
  say `VALIDATED`; ones transcribed from vendor documentation say
  `DOCUMENTED` and invite you to treat the match as provisional.
- **Open questions.** Reports never paper over gaps — each question lists
  the concrete steps that would answer it ("Resolves with: …").

---

## 5. The interactive console (`tui`)

```bash
portallens tui \
    "http://maz.wifi/login?dst=..." \
    "https://captive.ispman.tech/hotspots/.../select?..."
```

The TUI runs the same analysis as `analyze`, then opens an interactive
terminal console with:

- a **relationship tree** (the one screen that beats Markdown),
- **confidence-badged observations**,
- the **evidence list**, and
- **open questions**.

It is a pure presentation layer — it renders a `PortalReport` the engine
already produced and contains no analysis logic. It is responsive from
~40 columns (Termux, portrait) to wide desktop: panels stack on narrow
terminals and sit side-by-side on wide ones. Severity and status are
never colour-only — every confidence badge carries its label text next to
its percentage.

Requires the `[tui]` extra: `pip install -e ".[tui]"`. Quit with `q` or
`Ctrl+C`.

---

## 6. Saved investigations and analysis steps

Analysis can be persisted instead of printed. An **investigation**
outlives the process — it has an id, keeps the report, and an audit log
of what was done.

### The workflow

```bash
# 1. Analyze and save; prints the new investigation's id
portallens investigate \
    "http://maz.wifi/login?dst=..." \
    "https://captive.ispman.tech/hotspots/.../select?..."

# 2. List saved investigations, newest first
portallens investigations

# 3. Re-render a stored report
portallens show <id>

# 4. Show the audit trail instead
portallens show <id> --audit

# 5. "Pull the thread": run a registered analysis step against the saved
#    investigation. Evidence is appended, findings recomputed, and the
#    report is re-saved automatically.
portallens step <id> resolve_dns
portallens step <id> ip_asn_lookup
```

The two registered steps today:

| Slug | What it does | Active? |
|---|---|---|
| `resolve_dns` | A/AAAA resolution of the investigation's hosts (stdlib) | yes — needs `--authorized` |
| `ip_asn_lookup` | RIPEstat ASN / holder lookup for the hosts | yes — needs `--authorized` |

`portallens step <id> <slug>` without `--authorized` refuses cleanly
(exit code 2) rather than silently doing nothing. Unknown slugs are
reported with the steps the investigation's open questions actually name.

The database lives at `$XDG_DATA_HOME/portallens/investigations.db` by
default — override with `--db <path>` or the `$PORTALLENS_DB` env var.
It is plain SQLite (no server), so it works on the desktop and on a phone
under Termux.

---

## 7. Active analysis: the `--authorized` flag

Everything active — HTTP fetching, DNS resolution, port scanning, OSINT
lookups, and the bypass probes — is gated behind **one flag**:

```bash
portallens --authorized "https://example.com/login"
```

`--authorized` is shared by `analyze`, `tui`, `investigate`, and `step`,
and it unlocks *every* active technique (ADR-15). The default policy is
fully **passive** — no network access without the flag.

With `--authorized`, `analyze` additionally runs the **NetAudit** pass:
bounded probing of well-known gateway admin ports (MikroTik WebFig/API,
SSH, Telnet) that can fire the `gateway_admin_exposed` security finding.
OSINT lookups (RIPEstat) run as `portallens step <id> ip_asn_lookup`
against a persisted investigation rather than inline.

> **You are responsible for targets you authorize.** `--authorized` is
> an assertion, not a verification — the tool cannot check that you own
> the network. See [section 11](#11-responsible-use).

---

## 8. Bypass detection probes (library)

`portallens.security` exposes **five bounded, authorized probes** that
answer only whether a bypass condition *appears possible*. Each requires
`AcquisitionPolicy(authorized=True)`, has a deliberately small
target/port surface, and returns `list[Evidence]` — including negative
and inconclusive results. No probe submits credentials, authenticates,
alters server state, or attempts to obtain access.

| Probe | Signature | What it does |
|---|---|---|
| `connect_test` | `connect_test(proxy, target, policy, *, connect_request=None, timeout_seconds=2.0)` | One HTTP CONNECT request; a 2xx response is potential tunnel-bypass evidence |
| `dns_tunnel_test` | `dns_tunnel_test(hostname, policy, *, resolve=None, captive_addresses=())` | One bounded A/AAAA lookup; a normal answer suggests DNS is not walled-gardened |
| `click_through_test` | `click_through_test(target_url, portal_host, policy, *, request=None)` | Single GET with redirects; reaching a non-portal host is potential click-through bypass |
| `port_scan_test` | `port_scan_test(host, policy, *, ports=DEFAULT_BYPASS_PORTS, probe_port=None, max_ports=16)` | Bounded list of common egress ports (default `53, 80, 443, 8080, 8443`); never scans a range |
| `parameter_tampering_test` | `parameter_tampering_test(portal_url, policy, *, parameters=None, request=None, sentinel=...)` | Baseline GET vs. benign navigation-parameter mutations; credential/token fields are refused |

Every network function is **injectable** — pass a `connect_request`,
`resolve`, `request`, or `probe_port` callable for controlled testing
against a capture instead of a live network.

A minimal example:

```python
from portallens.portal import AcquisitionPolicy
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.security import port_scan_test

policy = AcquisitionPolicy(authorized=True)
evidence = port_scan_test("192.0.2.1", policy)   # replace with a host you are authorized to test
for ev in evidence:
    print(f"[{ev.type.value}] {ev.key}: {ev.value}")
```

### Turning probe evidence into findings

Two helpers in `portallens.security` connect probe evidence to reports:

```python
from portallens.security import detect_bypass, merge_bypass_evidence

# 1. Produce findings from positive bypass evidence already on a report
findings = detect_bypass(report)

# 2. Or immutably attach evidence + derived findings to a new report copy
merged = merge_bypass_evidence(report, evidence)
```

### Interpreting results

Bypass findings mean **potential** bypass only:

- CONNECT success, DNS resolution, click-through, and parameter mutation
  results require independent verification before drawing conclusions.
- An open port is informational prerequisite evidence — reachability does
  not prove unauthenticated application traffic works.
- The probes never authenticate, and the passive analyzer never invokes
  them automatically: probes are caller-driven by design (ADR-18).

---

## 9. Using PortalLens as a library

The engine is a plain Python API — no CLI needed.

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

Render in SARIF instead:

```python
from portallens.reporting import render_sarif

print(render_sarif(report))
```

Or open the report in the TUI (requires the `[tui]` extra):

```python
from portallens.tui import PortalLensApp

PortalLensApp(report).run()
```

For active analysis from the library, pass the policy in the context:

```python
from portallens.portal import AcquisitionPolicy, AnalysisContext

report = portal.analyze(
    AnalysisContext(urls=["https://example.com/login"],
                    policy=AcquisitionPolicy(authorized=True))
)
```

---

## 10. Troubleshooting

**`portallens: command not found`** — the venv is not activated, or the
package isn't installed. `source .venv/bin/activate` (or
`.venv\Scripts\activate` on Windows) and re-check
`pip install -e .` from the repo root.

**`portallens tui` prints an install hint and exits** — the `[tui]` extra
is missing. Install it: `pip install -e ".[tui]"`.

**`No investigation with id ...`** — the id was mistyped, or the store is
at a different path. Check `portallens investigations`, and remember the
`--db`/`$PORTALLENS_DB` override if you used one when saving.

**`Unknown analysis step ...`** — the slug isn't registered. The error
message lists the steps this investigation's open questions name
(`resolve_dns`, `ip_asn_lookup` today).

**An active step refuses without `--authorized`** — expected. Add
`--authorized` only if you are authorized for the target.

**Report shows a platform as "documented only"** — that signature was
transcribed from vendor documentation and has not yet been validated
against a real captured URL. Treat the match as provisional; see the
report's provenance note.

---

## 11. Responsible use

PortalLens is intended for:

- **Operators** assessing their own captive portals before deployment.
- **Security researchers** with explicit, written authorization to assess
  a target.
- **Network auditors** producing evidence-backed reports for responsible
  disclosure.

**Do not run active analysis against networks you do not own or have
explicit written permission to assess.** The `--authorized` flag is the
single gate for every active technique (HTTP fetching, DNS resolution,
port scanning, OSINT, bypass probes) — and it is your assertion, not a
verification. Passive analysis (URL parsing, no network access) is always
safe and is the default.

PortalLens does not bypass authentication, and its bypass probes never
submit credentials or attempt to obtain access. Bypass findings are
"potential" by design and require independent verification.
