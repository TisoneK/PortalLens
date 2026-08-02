# Session 20 Review — bounded captive-portal detection

## Executive Summary

Implemented the next safe Wi-Fi vertical slice: bounded, authorized captive-portal connectivity probes with platform profiles, RFC 8908 metadata parsing, redacted status/redirect evidence, and a passive analyzer handoff seam. The slice does not connect to networks, follow redirects, open a browser, accept credentials, invoke bypass probes, or persist live events.

## Discovery and Research

- Existing Wi-Fi adapters are read-only and expose scan/status through a dependency-free `WifiAdapter` contract.
- `WifiConnection` already contains explicit lifecycle states and persistence-safe URL redaction.
- Existing acquisition policy is a single `AcquisitionPolicy(authorized=True)` gate; passive analysis remains the default.
- Research consulted RFC 8908 (Captive Portal API), RFC 8910 (DHCP/RA provisioning), platform probe behavior, and httpx redirect/streaming/timeout behavior.
- The current implementation uses fixed legacy profiles for Windows, Apple, Android (two documented endpoints), GNOME, and Firefox. RFC 8908 payload parsing is implemented; RFC 8910 option decoding is intentionally deferred.

## Baseline Health

- Baseline before changes: 263 tests passed.
- Final: 292 tests passed.
- Ruff: clean.
- Strict mypy: clean across 45 source files.
- `git diff --check`: clean.

## Findings and Fixes

### High — arbitrary legacy probe profile could become an SSRF primitive

**Fix:** Legacy probes now canonicalize against the built-in allowlisted profile set. Arbitrary caller-created URLs are rejected before the request.

### High — repeated captive detection could fail lifecycle transitions

**Fix:** Applying the same captive result to an already-captive connection is idempotent; changed portal metadata is safely redacted and replaced.

### Medium — probe error statuses were overclassified as captive

**Fix:** Redirects with a valid HTTP `Location` confirm captivity. 404/500, redirect-like statuses without a valid location, and unexpected body responses are unknown rather than confirmed captivity.

### Medium — RFC 8908 response trust and content type

**Fix:** RFC API responses require `application/captive+json` and an HTTP 200 response. Portal API URLs must be absolute HTTPS URLs without credentials. The endpoint is caller-supplied only with an explicit `provisioned=True` assertion documenting trusted DHCP/RA or equivalent OS provenance; the implementation does not claim to parse RFC 8910 yet.

### Medium — sensitive redirect and portal URL values

**Fix:** Location targets, RFC user-portal URLs, manual analyzer handoffs, and connection transitions pass through existing persistence-safe redaction. Fragments, credential-bearing URLs, sensitive query keys, nested URLs, and high-entropy path segments are not retained raw.

### Low — response growth and cancellation

**Fix:** HTTP requests disable redirects, use an explicit timeout, stream bodies with a hard byte ceiling, poll `CancellationToken`, and conservatively mark exact-cap responses truncated.

## Product Changes

- Added `src/portallens/wifi/captive_portal.py`.
- Added captive-portal evidence types.
- Exported detector/profile APIs from `portallens.wifi` while keeping Textual out of core imports.
- Added public `safe_portal_url` wrapper for reuse at the detector boundary.
- Added 29 deterministic tests covering profiles, authorization, redirects, status classification, cancellation, limits, RFC 8908 JSON, content type, redaction, state application, SSRF allowlisting, and passive analyzer handoff.
- Updated README and changelog with the library-only scope and deferred work.

## Deferred Work

- Wire the detector into selected-network session generations and the Textual picker/TUI.
- Add redacted Wi-Fi live-event persistence and SQLite migration.
- Implement RFC 8910 DHCP option 114 / DHCPv6 / RA option decoding or a typed OS-provisioned endpoint source.
- Add distro-specific Linux connectivity profiles only when their endpoint and success-body contracts are verified.

## Recommended Next Step

Build the generation-guarded selected-session worker around this detector, with cancellation and event emission first; then add the SQLite migration for scan, connection, portal, cancellation, switch, and worker-failure events.
