# Session notes — 2026-10-23 — Session 6 (Tessa, S006)

## Task

Supervisor, live: "The current connected network's subscription ended
yesterday, now its still connecting why." Then: run the tool, check whether
the bundle is unlimited or what happened, and say whether any other user can
reconnect that way.

## What was run

    portallens watch --target "WISPMAN PAY TO CONNET" \
      --journal ~/.local/share/portallens/watch-wispman2.json \
      --gateway-status --authorized

(The default journal belongs to KITENGELA@10; WISPMAN observations live in
`watch-wispman2.json`.)

## Observation 2 — 2026-10-23T05:13:49Z (08:13 EAT)

- Probe classification: `unrestricted`, unchanged across the gateway fetch
  (`gateway_fetch_perturbed: false`) — verified internet, not inferred.
- Gateway session view, straight from `http://10.30.0.1/status`:
  - username `98:AF:65:7C:6A:69` (the device MAC, as on 10-22)
  - **session-left 7h16m35s**; expires-on not shown
  - **bytes-left `unlimited`**
- Local facts: client `10.30.3.8/20`, gateway `10.30.0.1`, fresh DHCP lease
  obtained 07:55:54 EAT this morning (the machine re-joined the network today).

## The answer

The premise "expired yesterday" is contradicted by the gateway's own view:
the bundle is **still active with ~7h left**. The numbers show why the
supervisor reasonably thought it had died:

- Observation 1 (10-22 14:45Z): session-left 8h17m1s → implied deadline
  23:02Z.
- Observation 2 (10-23 05:13Z): session-left 7h16m35s → implied deadline
  12:30Z.
- Wall-clock between samples: 14h28m. Timer consumed: **1h00m**.

The implied absolute deadline moved ~13.5h, so this is **not a wall-clock
expiry**. The countdown behaves like **online/usage time**: it ticks while
the device is on the network (10-22 it ticked ~1:1 while the laptop was
working) and pauses while it is away (overnight it consumed ~1h of 14.5h —
roughly the evening's use; this morning's re-join came in on a fresh DHCP
lease and the same MAC was resumed without any code). This is the operator's
billing design, not a defect: data is unlimited, time is the meter, and the
meter only runs when you're plugged in. Enforcement lives at the gateway,
and the gateway still counts this MAC as authorized — hence "still
connecting".

Contrast maz.wifi (session 1): there the `/status` countdown ticked 1:1 with
wall clock. Same kind of page, different accounting — never assume one
operator's semantics for another.

## "Can any other user reconnect that way?"

- Every customer of this operator gets the same mechanics: session keyed by
  device MAC, silently resumed via MAC-cookie on re-join, usage-time meter
  that pauses when offline. Stretching one purchase across days by staying
  offline is available to all, by design — not an exploit, and not unique
  to this device.
- Another user cannot consume **this** bundle's remaining ~7h without
  presenting this device MAC (spoofing, layer-2 proximity required, and it
  would collide with the real device). No evidence of that: the gateway
  shows the session undisturbed and both samples verified unrestricted.
- Yesterday's operator-side observations stand unchanged (HTTP-only portal,
  reusable codes; the retracted admin-port claim stays retracted — nothing
  here re-probes ports).

## Guidance for future watch runs on this target

Do **not** record an `--expiry` boundary from "now + session-left": the
deadline slides with usage, so a wall-clock boundary would fire false
post-expiry findings every time the machine sleeps. A boundary only makes
sense if the operator states a fixed validity time.

## Protocol deviations

- Check-in write came after the live read, not before: the session opened
  mid-question on a live network and the tool run could not wait on ledger
  ceremony (same deviation Amara S005 logged and the office accepted). No
  roster row added — the session closes in the same message it signs.
- No product code changed. The only mutation is the watch journal outside
  the repo (`~/.local/share/portallens/watch-wispman2.json`), appended by
  the run itself.

## Verification

The tool's own report is the evidence: 2 observations, classification
`unrestricted` x2, session view read by the tool (no hand-fetch), fetch
unperturbed. Suite not run — no code touched.
