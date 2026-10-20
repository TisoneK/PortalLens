# Backlog (work queue — actionable items only)

The queue of work a session can pick up and **do**. One row per item, in
its priority table. It is a queue, not a knowledge base: the test for a
row is "can an agent start on this and finish it?" If the answer is no —
it's a finding, an open question, an advisory "should we…?", a deferred
"someday" idea — it belongs in [`parking-lot.md`](parking-lot.md), not
here. Writing discoveries into the backlog is how a queue turns into a
57-row document nobody can work from.

**Done = delete the row. Stale = delete the row.** The backlog holds
open, actionable work only. When an item is finished, delete its row —
the completion record is the finishing session's `agents/sessions.md`
entry and the commit, never a tombstone here. When an item stops
mattering, delete it too; if it still carries information worth keeping,
move it to the parking lot first. Git history keeps every removed row,
so deleting loses nothing. (The one thing you must not do is delete a row
whose work is genuinely still open and recorded nowhere else — a row
vanishing from the diff with no session entry or promotion behind it is a
dropped handoff, not cleanup. Legacy checkbox-format backlogs:
`ledger-mem closeout` sweeps checked-off `- [x]` tombstones a session
left behind — dry run by default; `--confirm` deletes.)

**The queue is capped at ~20 rows** (`backlog_cap` in
`workflows/history.conf`; `ledger-mem check` warns past it). Twenty is a
working set, not a limit to fill. When you'd add a 21st actionable item,
prune one first: the lowest-value open row goes to the parking lot
(deferred, still valuable) or is deleted (no longer relevant) — never a
row you can't justify dropping. A queue you can hold in your head beats
a comprehensive one you can't.

**Only actionable work, and context lives where the work is.** Every row
gets a stable **ID** — `B-<added YYYY-MM-DD>-<n>`, n = that date's next
sequence in the file — and a **Summary** cell that says what to *do*, not
everything known about it. A fresh agent should be able to start from the
one line; the deep context belongs in the linked issue, PR, ADR, or
parking-lot finding the row points at, not packed into the cell. Keep
status qualifiers short ("partial", "blocked on X"). Don't append
research narrative to a row to "preserve" it — that's the parking lot's
job.

**Priority is the table an item sits in (High / Medium / Low), and it is
dynamic.** Only the top of the queue really matters — when you start a
session, the handful of High rows (roughly the top 3–5) are the work; the
rest is context, and a row that has sat in Low for many sessions is a
candidate for the parking lot, not a permanent resident. When unsure
between two tables, pick the lower one; promoting a row later is cheap,
and a backlog where everything is High says nothing.

This backlog belongs to the **current office**. When the office closes,
open items do not carry over implicitly — the closing session re-seeds
into the new office's backlog **only items with an active owner or a
clear next step**; everything else is recorded in the permanent record
(`history/office-<NNN>.md`, "Open threads") or parked. A re-seeded row
describes the work in plain words and never cites the old office's
session numbers or codenames.

Full spec: `.context_ledger/core/schemas/ledger-schema.md` →
"The backlog: a capped work queue" and "The parking lot".

## Open Items

### High Priority

| ID | Summary |
|----|---------|
| B-2026-10-20-2 | Wire captive-portal detection into the Wi-Fi session controller with generation guards, cancellation and host-status gating (see ADR-23, ADR-24) |
| B-2026-10-20-3 | Back-port the two Context Ledger defects to the upstream package: `ledger-sync rename` vs `ledger-guard push-check`, and `migrate`'s missing backfill of collaboration/README.md and workflows/gates.conf (detail in the frozen office-001 flaws log) |

### Medium Priority

| ID | Summary |
|----|---------|
| B-2026-10-20-15 | Surface the post-expiry watch in the live console and attach its finding to a persisted investigation |
| B-2026-10-20-4 | Append redacted Wi-Fi live-event persistence: SQLite migration plus event path for scans, connection states, portal detection, cancellation and target switches |
| B-2026-10-20-5 | Parse RFC 8910 captive-portal provisioning (DHCPv4 opt 114, DHCPv6 opt 103, IPv6 RA opt 37) into a typed, provenance-carrying endpoint source |
| B-2026-10-20-6 | Validate the three documented-only signatures (CoovaChilli, UniFi, Meraki) against real captures, then flip their provenance to validated (ADR-6) |
| B-2026-10-20-7 | Build Certificate Transparency log mining behind the single authorization flag, feeding SAME_OPERATOR / USES_PLATFORM inference |
| B-2026-10-20-8 | Expose the five bounded bypass probes as CLI commands or registered analysis steps that persist evidence under `--authorized` |
| B-2026-10-20-9 | Calibrate bypass verification with controlled redirect-chain fixtures and caller-supplied response markers (ADR-18: transport signals stay provisional) |

### Low Priority

| ID | Summary |
|----|---------|
| B-2026-10-20-10 | Build DisclosureDesk: disclosure-state machine and report generation on top of the persisted investigation (ADR-8, ADR-17) |
| B-2026-10-20-11 | Add a `co_host_enumerate` analysis step: PTR lookups plus aggregation of hostnames sharing an address |
| B-2026-10-20-12 | Add bounded service-banner detection to NetAudit (connect-only, sequential, never authenticating) |
| B-2026-10-20-13 | Write the three per-action reviews required before code: default-credential authentication, L2 MAC impersonation, captured-token replay (ADR-19 is the exemplar) |
| B-2026-10-20-14 | Verify distro-specific Linux connectivity profiles before adding any beyond the current generic set |

<!-- TEMPLATE — add one ACTIONABLE row to the matching priority table
     (a finding, question, or someday idea goes in parking-lot.md instead):
| B-<YYYY-MM-DD>-<n> | <what to DO, one line, pointing at the issue/PR/
      parking-lot finding for detail — not the full context> |
-->
