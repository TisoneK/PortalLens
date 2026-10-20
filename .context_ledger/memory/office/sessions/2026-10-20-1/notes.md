# Session Notes: 2026-10-20 — Session 1

---
## 2026-10-20 — Rhoda / model not exposed (Session 1, office 002)

**Task.** Take over the uncommitted connectivity-watch slice left by the
session that died at the office close, answer the user's actual question
(what makes a hotspot keep giving access after a paid package expires), and
make PortalLens detect it rather than merely fingerprint the portal.

**What the takeover found.** The prior slice was sound: `ConnectivityWatch`
accumulates bounded probe results across connection epochs, takes expiry and
renewal as user annotations, and emits `watch:*` evidence that a registered
`post_expiry_access` check turns into a finding. 27 tests, all green. But it
was library-only: neither the CLI nor the TUI could reach it, so "I have a
tool for this, it should have caught this" was still true.

**What this session added.**
- `portallens watch`: one bounded probe per invocation, persisted to a
  journal (`$PORTALLENS_WATCH` / XDG path / `--journal`), so each real
  reconnect is a separate run with `--reconnect`. A journal is labelled by
  target and a mismatched target is refused instead of mixing networks.
- Journal serialization on `ConnectivityWatch` (`to_journal`/`from_journal`
  with validation, atomic save) and `render_watch_markdown` in reporting.
- `--format json` for scripts; the markdown report leads with findings,
  then boundaries, observations, transitions and the supporting evidence.
- 12 CLI tests (authorization refusal, accumulation across reconnects,
  renewal coverage, target mismatch, bad input, JSON) and docs.

**Verified.** Full suite 348 passing; ruff and mypy strict clean (47 source
files); a real `portallens watch` run against the default profile classified
the connection `unrestricted` and raised the finding against a 2020 expiry,
which is the end-to-end behaviour that was missing.

**Diagnosis recorded** in `tasks/parking-lot.md` P-2026-10-20-1: the five
mechanisms that fit "access stops at expiry, returns after reconnect", with
the reasoning that a stale session alone would not survive a reconnect, so a
re-authorizing mechanism (MAC cookie, ip-binding, grace profile, stale
accounting) is the better fit. Distinguishing them needs the operator's
side; a customer can establish the observable pattern, which is what the
watch records.

**Left open.** The watch is not surfaced in the live console and its finding
is not attached to a persisted investigation — queued as B-2026-10-20-15.
The check is `Provenance.DOCUMENTED`, so the finding prints as provisional
until validated against a real capture (consistent with ADR-6).


## Live measurement on maz.wifi (2026-10-21 01:00-01:07 EAT)

Device: MAC 04:ED:33:76:D9:A0, IP 10.111.78.164 (the user's own device, on the
network with their permission).

| What was read | Result |
|---|---|
| Connectivity probe (Windows NCSI) | `unrestricted`, before *and* after fetching the portal |
| `maz.wifi/status` (MikroTik) | `Connected / left: 2h13m30s / 7m56s` -- a real countdown, 1:1 with wall clock |
| `maz.wifi/login` | 414-byte redirect stub |
| ISPMan `/ispman-paid/select` | 200, price list only; "If you already paid just click the package paid for to auto connect" |
| `/ispman-paid/usage/payments` | **"Nothing here yet."** |
| `/ispman-paid/usage/connects` | **"Nothing here yet."** |
| `/ispman-paid/usage/sessions` | history 7 Sep -> 20 Oct 19:48; 78.42 GB all-time, 47.18 GB in 30 days |

### What it establishes

1. **The access is bounded, not free.** The gateway itself reports a remaining
   time budget. Uptime 2h13m30s at 01:02:08 with 7m44s left implies a ~2h21m
   authorization -- not one of the sold packages (30 min, 1 h, 4 h, 6 h, 12 h,
   24 h, 2 d, 3 d, 1 wk, 1 mo). So the session was granted by the gateway's own
   `session-timeout`, not bought.
2. **The portal's claim contradicts verified access.** The same device is told
   it must buy a package while carrying 1.5 GB of traffic at that moment. This
   is exactly the `portal_claim_mismatch` the watch now emits.
3. **Fetching the portal did not revoke access.** Unrestricted before and after,
   so an unauthenticated portal GET from an authorized device is not itself
   disconnect trigger #2.
4. **No payment record exists for this MAC** -- but see the caution below.

### Caution on the "no package" reading

The payments list is empty *per MAC*. Billing may be account-level (the portal
labels this device `MAZ-U3LMJY`), so "nothing here yet" is evidence that no
per-device purchase backs the traffic -- not proof the operator received no
money. Before calling the access unentitled, reconcile the account ledger.

### Working answer to "why does it allow access without a package"

Not unlimited access: a **re-issued, time-boxed gateway session**. MikroTik
authorizes the MAC for a fixed budget that the gateway counts down (observed
~2h21m), independent of any purchase. Each re-authorization (reconnect, or the
gateway re-issuing after the budget expires) restarts that clock, so the device
"has internet" again without a package -- and when the clock or the session is
reset, the portal shows the price list, which the user experiences as
"disconnected and asked to buy". The enforcement is the countdown; the anomaly
is its renewal without a corresponding payment.

### Trigger #2 needs a second device

The user reports that another device joining their hotspot gets redirected to
the packages page and knocks the first device offline. Not reproducible from a
single device; requires a second client to authorize while this one holds a
session (queued as B-2026-10-21-02).
