# Changelog

All notable changes to PortalLens are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Technical detail lives in `.context/memory/reviews/`. This file is the
public-facing changelog — plain language only.

## [Unreleased]

### Changed

- **PortalLens is no longer built around a single portal provider.** Everything it knows about a platform — how to spot it, and how much each clue is worth — now lives in one place, so recognising a new provider is a matter of describing it rather than rewriting the analyzer. Reports on the portals PortalLens already understood are unchanged.
- **Reports say when a platform's description hasn't been checked in the real world.** Some descriptions come from a vendor's own documentation and have never been matched against a portal actually captured in the wild. Where that's the case, the report now says so and invites you to treat the match as provisional.
- **Two relationships were being listed twice** in every report that involved a hosted portal platform. Each is now listed once.

### Added (initial MVP)

- **Captive Wi-Fi portal analyzer.** Paste a captive-portal URL (or a pair: the local captive hostname + the external portal URL it redirected to) and PortalLens produces an evidence-backed Markdown report.
- **Platform fingerprints** for MikroTik RouterOS hotspots, ISPMan captive portals, and CoovaChilli — each with confidence scores.
- **Relationship inference** — REDIRECTS_TO, USES_PLATFORM, AUTHENTICATES_FOR, OPERATES_NETWORK, and a deliberately low-confidence RESELLS_BANDWIDTH hypothesis. Every relationship cites the evidence it rests on.
- **Confidence model** — every non-fact statement carries an integer score in `[0, 100]` plus a label (very_low / low / medium / high / very_high). Multiple evidence signals combine via a documented noisy-OR rule.
- **Passive by default.** No network access without explicit opt-in. Active techniques (HTTP fetch, DNS resolve, port scan) are gated behind an `AcquisitionPolicy` and require explicit `--i-have-authorization` on the CLI.
- **CLI** — `portallens <url> [<url> ...]` produces a Markdown report on stdout.
- **Library API** — `CaptiveWifiPortal().analyze(AnalysisContext(urls=[...]))` returns a `PortalReport` you can render, serialize, or inspect.
- **Plugin architecture** — the `Portal` base abstraction is broad enough that future portal types (web auth, payment, ISP) can be added as new plugins without rewriting the core.
- **`.context/` agent memory** — vendored protocol (core 0.2.0) for persistent AI agent memory across sessions.
