# Office 001 — accomplishments record (permanent)

- Opened: 2026-07-23
- Closed: 2026-10-20
- Sessions: 26

The frozen office lives at history/office-001/ until it is zipped into
archive/office-001.tar.gz. This record stays in history/ forever — even after
the tarball is garbage-collected, the office is never forgotten. Not read at
session start; deliberate lookback only.

## Accomplished

- Took PortalLens from an empty repository to a working Python library and CLI: `Portal` core abstraction, `captive_wifi` plugin, evidence model, confidence scoring, and Markdown/SARIF reporting.
- Provider knowledge became a declarative signature registry with per-signature provenance; ISPMan, MikroTik, CoovaChilli, UniFi and Meraki signatures are registered, the last three as documented-only until validated.
- Persisted investigations: SQLite document store with a real `PRAGMA user_version` migration ledger, an append-only audit log, and CLI verbs to create, list, show and step an investigation.
- Analysis-step registry with `resolve_dns` and `ip_asn_lookup`, computing the next investigation from structured open questions.
- Security module: registry of evidence-keyed checks, bounded NetAudit admin-port probing, five bounded bypass probes, and the assess-only boundary recorded in ADRs.
- Two generations of terminal UI: first a responsive report viewer, then a live investigation console with keyboard-driven steps, monitor and auto-run modes, then a setup front door.
- Wi-Fi stack: credential-free adapter contracts, read-only Windows/macOS/Linux discovery adapters, a generation-guarded picker/session controller, and bounded standards-aware captive-portal detection (RFC 8908).
- Documentation written for users rather than as a devlog: README, full tutorial, architecture notes, changelog.
- Protocol itself migrated from `.context/` core 0.5.0 to the Context Ledger `.context_ledger/` core 2.2.0, with the office layout, gates registry, guard hooks and generated entry points in place.
- Test suite grew from 55 to 336 passing, with ruff and strict mypy clean over the 47 source files.

## Decisions still in force

All 25 ADRs in the frozen `office-001/plans/decisions.md` were re-seeded
verbatim into the new office's `plans/decisions.md`; they remain binding.
The ones most likely to be tested by new work:

- ADR-1 / ADR-15 — passive by default; one explicit `authorized` flag unlocks active techniques, replacing the old per-technique tiers.
- ADR-2 / ADR-3 — noisy-OR confidence combination, with hypotheses capped at `low`.
- ADR-4 / ADR-5 / ADR-11 — `Portal` abstraction; provider knowledge and security checks are data registries, never per-vendor branches.
- ADR-6 — a signature's provenance is printed: a documented-only match says so in the report.
- ADR-8 / ADR-14 — `Investigation` is the persisted core; schema changes are appended to the migration ledger, never rewritten.
- ADR-12 / ADR-16 / ADR-18 — the assess-not-exploit ban is lifted as a records-level decision but nothing exploit-shaped has been built; bypass probing stays bounded, evidence-first and never authenticates.
- ADR-7 / ADR-24 — the TUI is presentation only (no analysis logic), and setup must stay honest about what is not yet implemented.
- ADR-20 / ADR-21 / ADR-22 / ADR-23 — Wi-Fi is credential-free, read-only adapters, discovery-only coordination, and bounded standards-aware detection.
- ADR-25 — rendered Wi-Fi rows are preserved across selection and refresh.

## Open threads

- **Work in progress at close — connectivity watch.** An uncommitted slice for the "hotspot keeps giving internet after a paid package expires" investigation was in the worktree: a `wifi/watch.py` module, its tests, a security-check addition, an export, plus CHANGELOG and tutorial copy. Its session never logged an entry; the frozen lock text is in `office-001/sessions/2026-10-20-24/notes.md`. The new office took the work over as its first session, with the raw diff intact and uncommitted.
- **Re-seeded into the new backlog** (actionable, with a next step): finish the connectivity watch; selected-session captive detection orchestration; redacted Wi-Fi live-event persistence; RFC 8910 DHCP/RA provisioning; verified distro-specific Linux profiles; validate the three documented-only signatures; CT-log mining; DisclosureDesk; reverse-DNS/co-host enumeration; service-banner detection; bypass-probe CLI orchestration; bypass verification calibration; the three per-action ADR-16 reviews (default credentials, L2 MAC impersonation, captured-token replay); and back-porting the two core defects logged during the migration.
- **Knowledge worth keeping, not queued:** HTML fingerprinting is cheaper via an `html_markers` registry field than per-vendor detectors; the signature provenance ledger still has no home; `web_auth` remains an unregistered portal type; mypy strict was never extended to `tests/` (the standing gate covers `src/` only); a `disclosure_state` column is the sanctioned way to make disclosure state queryable.
- **Two protocol defects found during the migration** (frozen in `office-001/flaws/log.md`): `ledger-sync rename` produces a commit that `ledger-guard push-check` always rejects, and `ledger-sync migrate` does not backfill `memory/collaboration/README.md` or `workflows/gates.conf`.
