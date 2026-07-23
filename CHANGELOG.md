# Changelog

All notable changes to PortalLens are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Technical detail lives in `.context/memory/reviews/`. This file is the
public-facing changelog — plain language only.

## [Unreleased]

### Added

- **Open questions now say what would answer them.** Every report ends with the gaps the analysis couldn't close — "who's the upstream ISP?", "is the admin panel exposed?". Each of those now carries the concrete follow-up steps that would resolve it (shown as "Resolves with: …"), and the ones that correspond to a specific missing link in the picture are tagged as such, so a future view can draw them as explicit unknowns rather than footnotes. Questions that can only be settled by capturing a real portal in the field say so by naming no automated step.
- **Saved investigations.** Analysis no longer has to be printed and lost. `portallens investigate <urls>` saves the result as an *investigation* that outlives the process — with an id, the report, and a history. List them with `portallens investigations`, re-open one with `portallens show <id>`, and review its trail with `portallens show <id> --audit`. Storage is plain SQLite (no server), so it works on the desktop and on a phone under Termux.
- **A recorded authorization trail.** Before running an active technique, you can record that you're authorized for it: `portallens authorize <id> --technique resolve_dns --note "customer confirmed"`. Each assertion is timestamped and kept in the investigation's audit log — because for a responsible-disclosure report, *when you were authorized to do a thing* is part of the evidence, not an afterthought.
- **Investigation-console TUI.** `portallens tui <urls>...` runs the same analysis as `portallens analyze` and opens an interactive terminal UI: a relationship tree (the one screen that beats Markdown), confidence-badged observations, the evidence list, and open questions — all in one scrollable view. The TUI is an optional extra (`pip install -e ".[tui]"`); the library and CLI keep their original dependency set if you don't install it. It works from ~40 columns (Termux, portrait) to wide desktop — panels stack on narrow terminals and sit side-by-side on wide ones. Severity and status are never colour-only; every confidence badge carries its label alongside its percentage.
- **CLI is now a command group.** `portallens analyze <urls>` (Markdown to stdout) and `portallens tui <urls>` (interactive console) are explicit subcommands. Passing URLs directly (`portallens <urls>`) still works — it routes to `analyze`, so existing scripts don't break.

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
