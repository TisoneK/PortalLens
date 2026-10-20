# Agent Sessions (append-only within the current office)

One entry per agent session in the **current office**, newest at the bottom.
Never edit or delete past entries — append corrections instead. This is not
append-only *forever*: when the office reaches `office_size` sessions (or a
milestone), `ledger-history close` freezes this whole office verbatim into
`.context_ledger/history/office-<NNN>/` (roster, registry, notes, logs —
nothing trimmed), writes the permanent accomplishments record
`.context_ledger/history/office-<NNN>.md`, and opens a fresh empty office
here. Closed offices in `history/` and `archive/` are never read at session
start. Before closing, note which open threads still matter — they are
re-seeded into the new office explicitly, and nothing else carries over.

<!-- TEMPLATE — copy below the last entry and FILL IN every placeholder:
---
## YYYY-MM-DD — Session N
- **Agent:** <name> | **Model:** <model id> | **Platform:** <machine/sandbox + OS> | **Role:** <engineer, or overlay from .context_ledger/core/roles/> | **Core:** <version from .context_ledger/core/VERSION>
- **Task:** <what this session set out to do>
- **Commits:** <count> (<first-sha>..<last-sha>)
- **Outcome:** <done / partial / blocked — one line>
- **Open items:** <pointers into tasks/backlog.md (actionable) or tasks/parking-lot.md (findings/questions), or "none">
- **Notes:** .context_ledger/memory/office/sessions/<date>-<N>/notes.md  (or "none")
- **Report:** .context_ledger/memory/office/reviews/YYYY-MM-DD-review.md
-->

---
## 2026-10-20 — Session 1
- **Agent:** Rhoda | **Model:** unknown (the harness does not expose a model id) | **Platform:** Tisone's Windows workstation (local) | **Role:** engineer | **Core:** 2.2.0
- **Task:** Takeover of the post-expiry connectivity watch: answer why a paid hotspot can keep giving access after expiry, and make PortalLens detect it end to end rather than only fingerprint the portal.
- **Commits:** `efff7ce` (office reset completion), `fd62389` (watch library + CLI) and the closing ledger commit
- **Outcome:** done — adopted the unfinished watch slice, added `portallens watch` with a target-labelled journal so observations survive across real reconnects, a watch report renderer, JSON output, 12 CLI tests and docs. 348 tests pass; ruff and mypy strict clean; a real run classified the connection and raised the finding. Recorded the five candidate mechanisms behind post-expiry access.
- **Open items:** B-2026-10-20-15 (surface the watch in the console and attach its findings to a persisted investigation). The check stays provisional until validated against a real capture (ADR-6).
- **Notes:** `.context_ledger/memory/office/sessions/2026-10-20-1/notes.md`
- **Report:** none (feature session — see the notes file and the changelog entry)
- **Extension (same session, after clock-out):** added the portal-claim dimension to the watch. A sample now records what the portal showed (`purchase_required` / `login_required` / `active_session` / `unknown`) plus a note, and `portal_claim_mismatch` fires when verified access and the portal's claim disagree — no expiry needed. The claim is recorded, never fetched: the user's second disconnect trigger implies an unauthenticated portal request can reset the session, so probing the portal would perturb what is being measured. 360 tests, ruff + mypy clean.

- **Extension (same session, live measurement):** read the operator's own views on `maz.wifi` -- ISPMan `/ispman-paid/select` (price list only), `/usage/payments` ("Nothing here yet"), `/usage/connects` (empty), `/usage/sessions` (7 Sep onward, 78.42 GB all-time) and the MikroTik `/status` page, which reports a `Connected / left` countdown (`2h13m30s / 7m56s`, ticking 1:1 with wall clock, ~2h21m total -- no sold package duration). Verified access was `unrestricted` before and after the portal fetch, so an unauthenticated portal GET does not itself reset the session. Conclusion recorded: access is a re-issued, time-boxed gateway session rather than unlimited free internet. Background watcher started across the budget deadline (01:09:50) to catch the transition.
