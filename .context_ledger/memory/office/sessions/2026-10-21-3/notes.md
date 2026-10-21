# Session notes — 2026-10-21 — Session 3 (Kwame, S003)

## Task
Tisone: connected to a portal network, has not made a subscription in a while,
does not know why. Use PortalLens to figure out why.

## Evidence gathered (observed facts)
- Current network: SSID `KITENGELA@10`, open 802.11 (no encryption), 5 GHz,
  BSSID 8c:83:e8:0f:df:7d. **Different operator than maz.wifi** (user-confirmed).
- Addressing: client `11.220.2.109/16`, gateway/DHCP server `11.220.0.1`,
  gateway MAC `dc:2c:6e:00:06:8c` → MikroTik. DNS handed out: 8.8.8.8,
  192.168.100.1 (operator caching resolver on a separate private subnet).
- DHCP lease obtained 2026-10-19 19:05:40 EAT, expires 2026-10-22 07:55:15
  (~36 h lease) — the device has been attached continuously for ~37 h.
- `portallens watch --target KITENGELA@10` (windows-ncsi profile): three
  samples, all verified **unrestricted** (05:20:52Z, 05:23:26Z, 05:29:51Z);
  no redirect observed, `portal_url` null, no RFC 8908 session data captured.
  Journal: `C:\Users\Lameck\.local\share\portallens\watch.json` (fresh, target
  had no prior history here).
- User-fetched MikroTik `/status` page (recorded as portal claim
  `active_session`, sample 3): USERNAME `UIBMX5SUY3`, MAC 98:AF:65:7C:6A:69
  (this machine), IP 11.220.2.109, PLAN empty, START-TIME empty,
  SESSION-LEFT / EXPIRES-ON / BYTES LEFT all "Not assigned *".

## Answer to the user's question
The gateway has this device inside an **active hotspot session whose user row
carries no plan and no time/byte limits**. Traffic is authorized at the
gateway, the portal never intercepts, so nothing ever prompts for a purchase —
that is why no subscription has been needed.

**Development:** the user identifies the session username `UIBMX5SUY3` as one
of their **M-Pesa transaction codes** (10-char uppercase alphanumeric format
matches exactly). The billing integration therefore created this session user
from a real past payment but attached no plan or limits — one payment became
an effectively unexpiring session, silently re-authorized (MAC-cookie) across
reconnects. Recorded as observation note in the watch journal.

## Scenarios (calibrated)
- **A (~75%)** — Paid session without limits: M-Pesa-integrated billing names
  the hotspot user after the transaction code and never attaches a
  profile/limits, so the payment authorizes access indefinitely. Supported
  by: user identification of the code, empty plan, all limits "Not assigned".
  Verify: find `UIBMX5SUY3` in the user's M-Pesa history (Safaricom app /
  statement) — its date is the true last-payment date; operator portal
  payments view should list the same code.
- **B (~15%)** — Operator-provisioned open access (known-customer free tier).
- **C (~10%)** — User misremembers the code; free/trial session after all
  (original hypothesis: random trial username, MAC-cookie keeps it alive).

Optional discriminating checks (user-side, browser): `/login` page for a
trial button; operator portal account/payments views.

## Protocol deviations this session
- `ledger-guard install` and `ledger-state generate` were blocked by the
  auto-mode permission classifier as out-of-scope for the diagnostic request;
  per the standing project memory the task ran first and ledger writes are
  batched at the end (this commit). STATE.md is therefore not regenerated.
- `git push` is blocked in auto mode (user-scope memory): the user must push,
  or approve via the harness permission prompt / switch mode.

## Follow-up candidates (backlog, not actioned)
- Surface a `no_plan_active_session` observation: the watch records claims but
  has no finding for "gateway session active with no plan attached", which is
  the post-paid-inverse of `portal_claim_mismatch`. Rhoda's maz.wifi work
  documented paid-invisible sessions; this session shows the complementary
  unpaid-but-authorized case on a different operator.
