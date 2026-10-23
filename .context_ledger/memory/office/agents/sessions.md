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

- **Extension (the renewal, caught live):** the watcher straddled the budget deadline. With 16s left at 01:09:35, the gateway at 01:09:56 reported a brand-new session (`3s / 1h38m19s`) while every connectivity probe stayed `unrestricted` -- no portal, no purchase, no user action. Session 1 (from 22:48:25) held 2h21m26s; the new one expires 02:48:15; the two sum to ~4h from the session start. So the device is spending a 4-hour entitlement in two server-issued sessions, and the portal never shows it. Queued the horizon test at 02:48:15: a third session would prove the grant is unbounded, access falling to the portal would prove the gateway enforces and only the portal's display is wrong.

---
## 2026-10-21 — Session 2
- **Agent:** Nadia | **Model:** unknown (the harness does not expose a model id) | **Platform:** Tisone's Windows workstation (local) | **Role:** engineer | **Core:** 2.2.0
- **Task:** Install the project's dependencies so the repo is runnable locally.
- **Commits:** 1 (this closing ledger commit; no product code changed)
- **Outcome:** done — built `.venv` on Python 3.14.7 and installed editable with the `dev` extra per `docs/TUTORIAL.md` (`pip install -e ".[dev]"`, which subsumes `tui`). Everything resolved from wheels, nothing needed a local build toolchain. Verified: `portallens --version` prints 0.1.0 and the full suite is 378/378 green in 26s.
- **Open items:** none. Worth noting for whoever next touches the toolchain config: the interpreter here is 3.14.7 while `pyproject.toml` declares `requires-python >=3.10` and `[tool.mypy]` pins `python_version = "3.10"`, so mypy is checking a 3.10 target against a 3.14 runtime — fine today, but a future 3.14-only stdlib change would surface as a mypy/runtime mismatch rather than a test failure.
- **Notes:** none
- **Report:** none (environment session — no product or design change to review)

---
## 2026-10-21 — Session 3
- **Agent:** Kwame | **Model:** unknown (the harness does not expose a model id) | **Platform:** Tisone's Windows workstation (local) | **Role:** engineer | **Core:** 2.2.0
- **Task:** Diagnose why Tisone has not needed a subscription lately on the currently connected portal network (KITENGELA@10), using PortalLens.
- **Commits:** 2 (`cbd83d4` check-in + this closing commit; both await push — auto mode blocks pushes, user action required)
- **Outcome:** done — `portallens watch` verified unrestricted access across 3 samples on KITENGELA@10 (MikroTik gateway 11.220.0.1, lease held since 2026-10-19 19:05 EAT). The user-fetched `/status` page shows an active session `UIBMX5SUY3` with empty plan and all limits "Not assigned"; the user identifies that username as one of their M-Pesa transaction codes. Working explanation (~75%): the M-Pesa-integrated billing created the hotspot user from a past payment but attached no plan or limits, so one old payment authorizes access indefinitely (silently re-authenticated via MAC-cookie). Recorded as portal claim + notes in the watch journal.
- **Open items:** user-side verification — find `UIBMX5SUY3` in the M-Pesa history to date the true last payment; backlog candidate recorded in the notes (a `no_plan_active_session` finding for sessions with no limits attached, complementing `portal_claim_mismatch`).
- **Notes:** `.context_ledger/memory/office/sessions/2026-10-21-3/notes.md`
- **Report:** none (diagnostic session — findings in the notes file and watch journal)
- **Push status (appended correction at clock-out):** all three commits — `cbd83d4`, `ff9b564`, `dd245e5` — pushed once the user lifted the auto-mode block; clock-out is the fourth.

---
## 2026-10-21 — Session 4
- **Agent:** Kwame (S003, checked back in) | **Model:** unknown (the harness does not expose a model id) | **Platform:** Tisone's Windows workstation (local) | **Role:** engineer | **Core:** 2.2.0
- **Task:** Automate the manual diagnosis steps from session 3 into the tool — the user: "most of the work was done by you and not the tool… Research is almost over now its time for development." Stance chosen with the user: the tool fetches, with a guard (not "user fetches, tool parses").
- **Commits:** 1 project commit (`a5d95ce`) + closing ledger commits
- **Outcome:** done — three slices shipped: (1) read-only local network snapshot on every watch run (SSID, addressing, gateway MAC/vendor via OUI table, DHCP lease, DNS) from host-OS facts, Windows-first; (2) `--gateway-status` (requires `--authorized`) fetches the MikroTik `/status` session view bracketed by two connectivity probes, with perturbation recorded as evidence either way — the validated session-reset hazard made the bracket mandatory; (3) two new evidence-keyed checks: `gateway_session_without_plan` (active session, no plan, all limits unassigned) and `session_username_payment_code_shape` (username matches the M-Pesa transaction-code shape). Journal format v2; v1 journals still load. Design recorded as ADR-28. 420 tests (baseline was 378), ruff + mypy strict clean.
- **Open items:** next live visit to KITENGELA@10 should re-run `portallens watch --target KITENGELA@10 --gateway-status --authorized` to confirm the tool now reproduces the session-3 findings unaided; session 3's user-side verification (find `UIBMX5SUY3` in M-Pesa history) still stands.
- **Notes:** `.context_ledger/memory/office/sessions/2026-10-21-4/notes.md`
- **Report:** none (feature session — ADR-28 plus the notes file)
- **Extension (same session, live validation):** the user's first live `--gateway-status` run fetched `/status` fine but parsed empty — the gateway serves it as a shell page whose iframe carries the real session view on the billing provider (`asp.billnasi.com/endpoints/status?username=...`, labels as `<th>` cells). Two fixes (`664de0c`): the fetch follows the shell's iframe exactly one level (same authorized, probe-bracketed action; report names the source URL; iframe-unreadable degrades to the username the shell URL leaks), and an empty parse is no longer silent — `watch:gateway-status-no-session` evidence plus bracket evidence fire regardless of session-view success (the no-evidence-at-all gating was the actual bug). Live re-run confirmed: the tool alone reproduced the session-3 findings — `gateway_session_without_plan` (85) + `session_username_payment_code_shape` (55) — with no classification change across the fetch. Suite at 429 tests, ruff + mypy clean.
- **Extension (same session, report voice):** the user flagged that the watch report addressed its reader as "you" and called operator annotations "user-recorded" — confusing for anyone reading a report they did not run. `0aabbf2` rewrites report-facing strings third-person ("the operator"); operator-facing `--help`/error text keeps its voice. 429 tests, ruff + mypy clean.

---
## 2026-10-22 — Session 5
- **Agent:** Amara (S005) | **Model:** deepseek-v4-flash | **Platform:** Tisone's Windows workstation (local) | **Role:** engineer | **Core:** 2.2.0
- **Task:** Two asks: analyse a newly joined network (`WISPMAN PAY TO CONNET`), then "fix all and push" — finish the digest slice S003 abandoned when it ran out of tokens.
- **Commits:** `1c10fa0` (digest + uncertainty wired end to end, `observed_at` on evidence), `a65e54a` (card-template session view), `3d67a83` (picker teardown race) + this closing ledger commit
- **Outcome:** done — 437 tests, ruff + mypy strict clean. S003's slice finished: evidence carries `observed_at` as data (the digest had been crashing on it), identical evidence rows group onto their observations, finding slugs and their own uncertainty survive both markdown and SARIF. Live defect found and fixed: `--gateway-status` reported "no session view" on WISPMAN while the gateway held a paid one — that operator renders the session as label/value cards, which the parser now reads (unknown cards cannot populate a field). The intermittent `test_picker_auto_refreshes_networks` failure was a real teardown race (timer firing into unmounted widgets), guarded at the render.
- **Network answer:** `WISPMAN PAY TO CONNET` is a **working paid bundle**, not an anomaly — MikroTik gateway `10.30.0.1` (Routerboard OUI), session username = device MAC, bundle time left ~9 h, data balance unlimited; the supervisor confirms the payment. Operator-side observations recorded: admin ports 8291/8728 reachable from the client /20, HTTP-only portal whose reusable access codes travel in clear text over an open network.
- **Open items:** none on the code side; KITENGELA@10's user-side M-Pesa lookup still stands. The next unfamiliar portal skin is the real test of the card map.
- **Notes:** `.context_ledger/memory/office/sessions/2026-10-22-5/notes.md`
- **Report:** none (feature + diagnosis session)

## 2026-10-22 — S005 follow-up: the tool reads the view itself

- **Correction to the entry above:** the operator-side sentence claiming admin ports 8291/8728 were reachable on `10.30.0.1` is **withdrawn**. No port probe was run and nothing in the journal or store records one (`investigations.db` empty). That was RouterOS default knowledge stated in the voice of a measurement; it is retracted here rather than edited out, because this log is append-only.
- **Why this follow-up exists:** the supervisor's point that the tool should have found the card-rendered session view, not the operator by hand. The earlier per-skin card map (closed label list behind a `font-bold` regex) taught it one skin. Replaced by a structural reader: `wifi/session_view.py` flattens the page with stdlib `html.parser`, pairs a label-ish text run with the run beside it inside the same container, and maps labels by meaning (`username`, `plan`, `expir`, `balanc`, `quota`…) with the value's shape breaking ties. Four live failures became tests: bundle-expiry outranking plan, a section heading stealing the next label, two-quantity cells, money as a data balance.
- **New report state:** a page with label/value pairs but no readable session identity raises `watch:gateway-session-view-unread` and the digest prints "session view unread" — a parser gap can no longer be printed as "no session view".
- **Live acceptance:** `watch --target "WISPMAN PAY TO CONNET" --gateway-status --authorized` read username `98:AF:65:7C:6A:69`, session-left `8h17m1s`, bytes-left `unlimited`, source `http://10.30.0.1/status`, fetch unperturbed, no findings — with no hand-fetch involved. One attempt died on a transient fetch timeout; the same call in-process succeeded in 0.9 s immediately after.
- **Checks:** 450 tests pass, `ruff check src tests` clean, `mypy` strict clean over 51 files; old journals load with `pairs_read: 0`.
- **Notes:** `.context_ledger/memory/office/sessions/2026-10-22-5/notes.md`

---

## 2026-10-23 — Session 6
- **Agent:** Tessa (S006) | **Model:** unknown (the harness does not expose a model id) | **Platform:** Tisone's Windows workstation (local) | **Role:** engineer | **Core:** 2.2.0
- **Task:** Live question on `WISPMAN PAY TO CONNET`: the supervisor believed the bundle expired yesterday yet the machine still connects — run the tool, say whether the bundle is unlimited or what happened, and whether another user could reconnect the same way.
- **Commits:** 1 (this closing ledger commit; no product code changed — the watch journal lives outside the repo)
- **Outcome:** done — the gateway's own session view contradicts the expiry premise: bundle **still active, session-left 7h16m35s, data unlimited** (source `http://10.30.0.1/status`, fetch probe-bracketed and unperturbed). The countdown is **usage time, not wall clock**: between the two observations 14h28m of wall time consumed exactly 1h00m of bundle time — the deadline moved ~13.5h. Overnight the machine was away; this morning it re-joined on a fresh DHCP lease and the MAC-keyed session resumed with no code. "Still connecting" because the gateway still counts this MAC as authorized.
- **Other users:** the mechanics (MAC-keyed session, MAC-cookie resume, meter pauses offline) apply to every customer by design — stretching a purchase across days is not an exploit. Someone else's device cannot consume this bundle without spoofing this MAC; no evidence of that.
- **Open items:** none. Guidance recorded: do not arm `--expiry` on this target from "now + session-left" — a sliding usage-time deadline would fire false post-expiry findings on every sleep.
- **Notes:** `.context_ledger/memory/office/sessions/2026-10-23-6/notes.md`
- **Report:** none (diagnostic session — the tool's own watch report is the evidence)
- **Extension (same session, KITENGELA@10):** the supervisor reconnected and the portal said **"You have unused voucher UIBMX5SUY3"** — clicked Connect, access worked — and confirmed SMART WIFI@5 is the same network as KITENGELA@10. Recorded with `--reconnect --portal active_session --note … --gateway-status` against the KITENGELA@10 journal: the run itself confirmed the alias (same gateway 11.220.0.1, same client IP/MAC, same billnasi backend) and the unchanged session view (`UIBMX5SUY3`, plan empty, all limits Not assigned). Session 3's hypothesis is confirmed: the voucher is never consumed — every session from it has no plan/limits, so the portal keeps offering it as "unused" forever. One purchase, indefinite reuse. Both findings re-fired (`gateway_session_without_plan` [medium, 100% provisional], `session_username_payment_code_shape` [low, 96%]).
