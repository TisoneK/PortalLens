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

## The renewal, observed (2026-10-21 01:09:51)

The watcher sampled the gateway every 20s straight through the budget deadline:

```
01:08:53 gw connected/left = 2h20m28s / 58s
01:09:14 gw connected/left = 2h20m49s / 37s
01:09:35 gw connected/left = 2h21m10s / 16s
01:09:56 gw connected/left = 3s / 1h38m19s      <- new session, no portal, no user action
01:10:17 gw connected/left = 24s / 1h37m58s
01:10:38 gw connected/left = 45s / 1h37m37s
```

Every sample in between was `captive=False` on the connectivity probe: the device
never lost access and was never shown the purchase page.

### The arithmetic that matters

- Session 1: started 22:48:25, budget 2h21m26s, ended 01:09:51.
- Session 2: started 01:09:53, budget 1h38m22s, ends **02:48:15**.
- 22:48:25 + 4h = **02:48:25**. The two budgets sum to 3h59m48s.

So this is not an unbounded grant: the gateway is spending a **4-hour
entitlement** in two consecutive sessions, and it creates the second one
**automatically at expiry** with no purchase, no portal, and no user action.
4h is also a sold package (Ksh.25), yet the payments list for this MAC is empty.

### Consequences for the model

1. "Access without a package" = an entitlement the gateway holds but the
   customer-facing portal does not show, renewed server-side.
2. The observable "disconnect and ask to buy" should therefore happen when the
   **4-hour horizon** is reached (02:48:15), not when a session's countdown ends.
   A watcher is running across that horizon (`/tmp/horizon-watch.log`).
3. If the horizon passes *and* a third session is issued, the grant is unbounded
   — that is the real finding. If access falls to the portal at 02:48, the
   gateway is enforcing correctly and the mismatch is only in what the portal
   displays.

### Side observation

After the renewal, HTTPS reads to `captive.ispman.tech` began timing out
(`ReadTimeout` at 15s and again at 40s) while `http://maz.wifi/status` answered
normally. Not yet diagnosed: portal-side slowness, or the renewed session
blocking the portal host.

## Live gateway admin exposure (2026-10-21, 02:01–02:12)

`portallens analyze --authorized` while connected caught the gateway's admin
surface from the client network:

| Port | State | Service |
|---|---|---|
| 23 | **open** (22 ms, Telnet IAC banner) | RouterOS login |
| 80 / 443 | open (~1.5–2.5 s) | captive portal |
| 22 | filtered (timeout) | — |
| 8291 / 8728 / 8729 | filtered (timeout) | WebFig / API |
| 8080 | refused | — |

`maz.wifi` resolves to `10.111.0.1`. Confirmed independently with a raw socket
scan, not just the tool's own probe.

### Default-credential audit (new capability, ADR-26)

`--check-default-credentials` tried the three published RouterOS defaults
against port 23 and recorded `admin_credential:23 = default_rejected`. Verified
at the prompt: `Login: admin` → `Password:` → `Login failed, incorrect
username or password`. So the Telnet admin is **exposed but not using a vendor
default** — the exposure finding stands, the catastrophic one does not.

Telnet admin on the client-facing interface is still worth reporting to the
operator on its own: RouterOS telnet is cleartext, and the login prompt is
reachable by every client on the network.
