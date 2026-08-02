# Session 14 — Plan-only refinement (2026-08-02)

> **Adjacent file in this directory:**
> - [research-questions.md](research-questions.md) — three Session-14
>   followups framed as research items (R1 ADR-shape decisions for
>   default-cred + MAC; R2 `co_host_enumerate` AnalysisStep design;
>   R3 pre-existing mypy-strict baseline). Read after this notes file
>   for the long-form research framing; read this notes file first
>   for the session narrative.

## User target

Refine the kickoff feature list (sections 1-5: active bypass verification,
gateway probing, parameter fuzzing, network mapping, intelligence
gathering) against the existing ADRs. Two confirmed decisions from
`ask_user`:

- **Refine the plan first** — no code this session.
- **Active attack features run behind the single `--authorized` flag** —
  ADR-15 model; one boolean unlocks every active technique.

## What this session changed

Six files modified, all `.context/memory/` (no `src/` touched):

- `tasks/current.md` — Session-14 plan-only lock message (replaces
  Session-13 lock).
- `tasks/backlog.md` — six entries appended at the end of the existing
  appendix, no edits to existing entries:
  - Reverse DNS / co-host enumeration (passive `AnalysisStep`)
  - Service banner detection on discovered ports (active, bounded)
  - ARP-based network enumeration (active, spec-only)
  - Per-action ADR-16 review: default-credential authentication
  - Per-action ADR-16 review: L2 MAC impersonation
  - Per-action ADR-16 review: captured-token session replay
    (ADR-19 drafted this session as the exemplar)
- `plans/decisions.md` — ADR-19 drafted: session-replay classification
  (synthetic approvable / owned-target approvable / captured-real
  refused). Status `proposed` pending user acceptance.
- `agents/sessions.md` — Session-14 entry appended (this file).
- `inefficiencies/log.md` — two honest-friction entries (str_replace
  duplicate-listing bug + `read_files` 20k-token truncation).
- `sessions/SUMMARY.md` — Session-14 row appended for continuity.

## Why no code was written

User explicitly chose "refine the plan first." Every kickoff feature
now has: classification (passive / active / research-only), explicit
authorization scope language, ADR-15 alignment, ADR-18 probe-only
cross-check, and where applicable a per-action ADR-16 meta-item.

## ADR-19 outcomes (in detail)

- **Synthetic replay** — caller supplies a synthetic token; PortalLens
  echoes it back to the portal endpoint to observe validation behavior.
  Approvable behind `--authorized`. The action does not cross
  ADR-18's "never attempt to obtain access" because the synthetic
  token carries no authorization to extend.
- **Owned-target replay** — operator replays a session token
  legitimately issued by the portal against their own authorized
  target. Approvable behind `--authorized` + per-target audit trail.
  Bounded by the authorization scope.
- **Captured-real replay** — replay of a token captured from a third
  party against that third party's portal. **Refused.** Operator
  authorization attaches to the target machine / network, not to
  credentials belonging to a captured user. Captured-user consent
  absent.

CLI surface anchored at this shape: `--replay-mode {synthetic, owned}`
(enum excludes captured-real by construction, not just runtime).

## Code-reviewer findings worth noting (not fixed in this session)

The code-reviewer agent (running against the changes post-write)
surfaced these structural observations. They are correct and worth a
clarification pass in a future session, but expanding them here would
have grown Session 14 beyond its plan-only scope:

1. ADR-19's **three-category shape may not transfer cleanly** to the
   default-credential and MAC-impersonation meta-items. Default-cred
   likely wants an auth-mechanism bucketed shape (HTTP-basic /
   HTTP-form / SSH-password / SSH-key / RADIUS); MAC likely wants a
   binary lab-vs-live shape (not three categories). The per-action
   *discipline* is the right inheritance; the *shape* of each ADR
   should be matched to the capability being assessed.
2. **Synthetic replay approval could be tightened** to explicitly state
   that the response observation ends the action — inferring a real
   token from response patterns would be a separate analysis step
   requiring its own ADR if desired. This is a guard against
   accidentally laundering probe output into exploitation input.
3. The kickoff item **"IP param tampering — can you claim someone
   else's IP?"** is ambiguous (raw-socket L3 source-IP setting vs
   URL-level tamper vs application-layer claim). The Session 13
   `parameter_tampering_test` covers the URL-level tamper shape; the
   other two interpretations are either root-restricted (raw socket)
   or ill-defined (app-layer claim). Needs the user's clarification
   before any IP-related backlog item lands.
4. **CT-log mining entry** (Session 3, still open) does not need a
   Session-14 update — the Session-12 footer notes that older
   ADR-13 tier references read through ADR-15. No plan drift.

## Session 15 candidates (in rough priority order)

1. **Accept/refine/reject ADR-19** — user decision required before
   any session-replay code lands.
2. **Draft the two per-action ADRs** for default-credential
   authentication and L2 MAC impersonation, in shapes appropriate to
   each (see finding 1 above).
3. **Passive `co_host_enumerate` step** — lowest-risk follow-on;
   follows the existing ADR-9 `AnalysisStep` shape (next to
   `resolve_dns` / `ip_asn_lookup`); no per-action ADR needed.
4. **CT-log mining** — already in backlog; implement once Session-15
   priorities clear.
5. **CLI/investigation orchestration for bypass probes** — Session-13
   open item, still standing.
6. **Clarify IP param tampering** — user clarification before any
   implementation work (finding 3).

## Open standing constraints this session upheld

- Secrets rules were not touched (the one non-overridable boundary).
- Append-only guarantees on `tasks/backlog.md` /
  `plans/decisions.md` / `agents/sessions.md` /
  `inefficiencies/log.md` were preserved (no edits or reorderings of
  earlier entries).
- ADR-1 architectural invariant (`acquisition/fetcher.py` is the
  ONLY outbound network surface; everything funnels through
  `assert_policy`) was not weakened.
- ADR-12 bounded-business-intelligence bound stayed in force
  (`RESELLS_BANDWIDTH` still capped at low, no org-profiling
  collectors introduced).
- README's "does not bypass authentication" wording was not updated
  (no exploit capability built — ADR-16 noted this is the rule that
  would change if/when exploit actions land).
