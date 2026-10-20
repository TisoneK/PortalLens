# Parking Lot (deferred knowledge — not a queue)

The backlog is a work queue you act on; this file is the knowledge base
you **don't** act on yet. Research findings, open design questions,
advisory "should we…?" items, deferred work, and someday ideas live here
so the backlog stays a queue an agent can actually work from. Nothing
here is urgent, nothing here is capped, and nothing here blocks a gate.
The record of a finding is its own row plus the commit / session entry
that produced it; git history keeps every row, so promoting or dropping
one loses nothing.

**One rule keeps the two files honest: a parking-lot row is not a task.**
If an item becomes actionable — it now has a clear next step and someone
to take it — **promote** it: cut the row here, add an actionable row to
`backlog.md` (a fresh `B-` ID, one line, pointing back at this row's `P-`
ID if the context matters), and leave it here only as a one-line
"→ promoted to B-… " stub if you want the breadcrumb. An item that turns
out to be wrong or moot is just deleted — history remembers it.

Every row gets a stable **ID** — `P-<added YYYY-MM-DD>-<n>`, n = that
date's next sequence in the file — and a **Summary** cell with enough
context that a future session can pick it up cold. Keep status
qualifiers in the text ("advisory", "needs a decision", "blocked on X",
"deferred by owner"). There is **no cap** here and **no priority** —
items are grouped by *kind*, because the whole point is that these are
not competing for the top of a queue.

This file belongs to the **current office**. When the office closes, the
parking lot is **not** re-seeded wholesale: the closing session promotes
what is now actionable into the new backlog and records the rest in the
permanent record (`history/office-<NNN>.md`, "Open threads"). A cold
idea earns its way into the next office by becoming work, not by being
copied.

Full spec: `.context_ledger/core/schemas/ledger-schema.md` →
"The parking lot".

## Findings

What we learned that isn't work yet — observations, measurements, root
causes, "the current design does X because Y".

| ID | Summary |
|----|---------|

## Open questions

Advisory questions, decisions still up for grabs, "should we…?" — a
question is not a task until it has an owner and a next step (then it
becomes a backlog row or an ADR in `plans/decisions.md`).

| ID | Summary |
|----|---------|

## Deferred work

Real tasks, consciously parked — not now, but keepable. This is where a
backlog row goes when the cap forces a prune and the item still matters:
out of the queue, not into the void.

| ID | Summary |
|----|---------|

## Someday

Loose ideas with no owner and no hook yet. The lowest-pressure shelf.

| ID | Summary |
|----|---------|

<!-- TEMPLATE — add one row to the matching section:
| P-<YYYY-MM-DD>-<n> | <enough context that a future session can pick
      this up cold — status qualifiers in the text; promote to the
      backlog when it becomes actionable> |
-->

---
## Findings

| ID | Finding |
|----|---------|
| P-2026-10-20-1 | **Why a hotspot can keep giving access after a paid package expires.** Five mechanisms fit the observed shape (access stops at expiry, returns after a reconnect, many customers affected): an expired session the gateway never tore down; MAC-cookie or device-based re-authorization restoring the device without re-checking the package; an IP-binding or trusted-device bypass; billing-to-RADIUS/router synchronization lag so the router still holds a valid authorization; or a free-access/trial/grace profile applied by policy. The reconnect detail matters: a stale session alone would not survive a reconnect, so a mechanism that re-authorizes the device (MAC cookie, ip-binding, grace profile, or stale accounting state) is the better fit. Confirming which one needs the operator's side (`/ip/hotspot/active`, `/ip/hotspot/ip-binding`, billing vs router logs); a customer can only establish the observable pattern, which is what the watch records. |
| P-2026-10-20-2 | **Two ways a connected device gets thrown back to the purchase page, and what they share.** (1) The user disconnects and reconnects deliberately. (2) A second device connects through the first (tethering) and is redirected to the packages page, which also drops the first device to the purchase page. Both are moments when a request reaches the gateway/portal carrying no valid session state: a reconnect starts a new lease/session, and the tethered device's HTTP arrives from the same MAC/IP but without the browser-side hotspot cookie, so the portal resolves it as unauthenticated. That the portal offers *purchase* rather than merely a login form suggests it maps "no session" to "no package", which is the same split state the `portal_claim_mismatch` check records. Testable prediction: a device with a package can be online while the portal's own page says no package, and the reverse (portal says active, gateway denies) should also occur; one of the two directions is the "free internet" the user reported. |
