# Backlog (append-only)

Open items for future sessions. Append at the bottom; never delete or
reorder. When an item is done, check it off and note the session/commit —
don't remove the line.

---
- [ ] **NetAudit module** (added 2026-07-23 by Super Z / Session 1) — active security-assessment surface, gated behind `AcquisitionPolicy` flags. The `acquisition/fetcher.py` is in place; what's missing is the security-audit analyzer that uses it. Pick a small, well-scoped first audit (e.g. "is the MikroTik admin interface exposed on the customer network?") and implement it as a separate `Portal` subclass or as a method on `CaptiveWifiPortal` that runs only when `AcquisitionPolicy.fetch_urls=True`. The user explicitly stated active analysis requires authorization — never run this against networks you don't own.

---
- [ ] **DisclosureDesk module** (added 2026-07-23 by Super Z / Session 1) — responsible-disclosure report generation + tracking. Extends `reporting/` with SARIF output and a disclosure-state machine (draft → submitted → acknowledged → fixed → published). The user's preference (in `user/preferences.md`) is that every finding states Title, Affected asset, Evidence, Impact, Confidence, Recommended remediation, and Verification status — DisclosureDesk should enforce that schema.

---
- [ ] **CoovaChilli fixture + tests** (added 2026-07-23 by Super Z / Session 1) — the test suite has a CoovaChilli fingerprint detector (`src/portallens/plugins/captive_wifi/fingerprints.py::_detect_coorvachilli`) but no CoovaChilli URL fixture in `tests/data/`. Find a real CoovaChilli captive portal URL (or construct one from the documented signature: `challenge` parameter, or `userurl` + `uamip` together) and add a `TestCoovaChilli` class to `tests/test_fingerprints.py` + `tests/test_url_parser.py`.

---
- [ ] **HTML fingerprinting** (added 2026-07-23 by Super Z / Session 1) — the `EvidenceType` enum already includes `HTML_ELEMENT` and `JS_BUNDLE`, but the analyzer doesn't yet capture HTML evidence. Wire up the `--html-file URL:PATH` CLI flag (the option exists in `cli.py` but the path→URL mapping is incomplete) and add an HTML fingerprint detector that recognizes ISPMan / MikroTik / CoovaChilli by their portal HTML signatures. This is the natural next step beyond URL-only passive analysis — still passive (user supplies the HTML), but much higher-fidelity fingerprints.

---
- [ ] **DNS resolution** (added 2026-07-23 by Super Z / Session 1) — `AcquisitionPolicy.resolve_dns` is defined but no code uses it. Add a `portallens/acquisition/dns.py` module that resolves a hostname (A / AAAA / CNAME / TXT) and emits `EvidenceType.DNS_RECORD` evidence. Use stdlib `socket` for A/AAAA, or `dnspython` for full record-type support. This is the lowest-risk active technique — DNS queries are not "probing" in any meaningful sense — but still requires explicit opt-in via the policy flag.

---
- [ ] **IP/ASN lookup** (added 2026-07-23 by Super Z / Session 1) — required to close the "who is the upstream ISP?" open question that every captive-portal report currently surfaces. Integrate a free IP/ASN API (e.g. RIPEstat `https://stat.ripe.net/data/whois/data.json`) behind `AcquisitionPolicy`. Emits `EvidenceType.IP_ASN` evidence. Once this lands, the analyzer can start emitting `UPSTREAM_OF` relationships with real confidence instead of leaving the question open.

---
- [ ] **SARIF output** (added 2026-07-23 by Super Z / Session 1) — for security-audit findings, SARIF is the industry-standard interchange format (GitHub code scanning, Azure DevOps, etc.). Add `render_sarif()` alongside `render_markdown()` in `reporting/`. SARIF is only meaningful once the NetAudit module produces actual security findings — passive analysis doesn't have findings to report in SARIF.

---
- [ ] **`web_auth` plugin** (added 2026-07-23 by Super Z / Session 1) — the `PortalType.WEB_AUTH` enum value is reserved but no plugin is registered against it. A natural second plugin: SSO / OAuth / OIDC login flows. The fingerprint + relationship model adapts directly — the URL signatures and platform detectors change (e.g. `client_id`, `redirect_uri`, `state`, `code_challenge` parameters for OAuth/OIDC), but the `Portal` abstraction doesn't. Implementing this would validate the plugin architecture's claim that new portal types slot in without an architectural rewrite.

---
- [ ] **Validate the three documented-only signatures** (added 2026-07-23 by Claude Code / Session 2) — `COOVACHILLI`, `UNIFI`, and `MERAKI` in `src/portallens/plugins/captive_wifi/signatures.py` carry `Provenance.DOCUMENTED`: their rules were transcribed from vendor documentation and have never been matched against a real captured URL. Each needs a capture added to `tests/data/`, a test class in `tests/test_signatures.py`, and then a flip to `Provenance.VALIDATED`. **This supersedes the session-1 "CoovaChilli fixture + tests" item by widening it to all three.** Until validated, every report those signatures fire on carries a note and an open question saying the match is provisional — do not remove that mechanism to make output look cleaner; it is the honesty guarantee the confidence model rests on (see ADR-5).

---
- [ ] **Decide where the signature provenance ledger lives** (added 2026-07-23 by Claude Code / Session 2) — the user's standing preference (`user/preferences.md`) is that fingerprint/signature knowledge accumulate in `.context/memory/` rather than being rediscovered per session. The runtime registry rightly lives in `src/` (it is executable data), but the *provenance* of each signature — which vendor doc or capture it came from, who validated it, against what URL, on what date — has no home yet and is exactly the kind of knowledge the preference is about. Decide whether `memory/` should carry that ledger, and if so seed it from the five signatures currently in the registry.

---
- [ ] **HTML fingerprinting is now cheaper — revisit the existing item** (added 2026-07-23 by Claude Code / Session 2) — the session-1 "HTML fingerprinting" backlog item predates the signature registry. It no longer needs a per-vendor HTML detector: add an `html_markers` field to `PortalSignature` plus one detector pass over the registry, and every registered provider gains HTML detection at once. Do this rather than writing `_detect_ispman_html()` and friends — that is precisely the pattern session 2 removed.
