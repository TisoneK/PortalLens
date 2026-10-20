# Session 11 — records-only security-constraint relaxation (2026-08-02)

## Target

`kickoff.md` target: "Remove any .context constraints that feel restrictive. The project should stay flexible."

## Ambiguity resolved (cost one ask_user round)

- First reading was **workflow ceremony** (push policy, reports, Phase-1 steps). Presented those options.
- User interrupted: **"I meant security constraints."**
- Re-scoped to the security posture recorded in `.context/`: ADR-1/10/12/13, `user/preferences.md`, `workflows/active.md`.

## Scope decisions (user-confirmed)

1. **Exploit scope:** *"Lift ban, build nothing yet"* — ADR-12's assess/exploit prohibition is removed as a standing rule; **no exploit capability is built** this session.
2. **Change scope:** *"Just the .context records"* — no `src/` changes, no test changes.

The earlier multi-select (consent tiers → one flag; drop auth ceremony; allow exploit actions; drop evidence schema) defined *which* constraints. Secrets rules were explicitly NOT selected — they are the one non-overridable boundary per the schema.

## What changed

| File | Change |
|---|---|
| `plans/decisions.md` | Appended **ADR-15** (single authorization, supersedes ADR-1/10/13), **ADR-16** (assess/exploit ban lifted — nothing built; supersedes the assess-not-exploit bound of ADR-12; the bounded-BI bound of ADR-12 stays standing per user), **ADR-17** (disclosure schema optional) |
| `user/preferences.md` | 3 bullets updated in place (single-auth, exploit-boundary-lifted, schema-optional) + new standing preference: keep `.context/` security constraints flexible |
| `workflows/active.md` | Focus areas rewritten to the relaxed posture; flags the code-alignment backlog item |
| `tasks/backlog.md` | Appended: align `src/` with ADR-15/16/17 |
| `tasks/current.md` | Set for this session (cleared at exit) |

## Deliberately NOT done

- No `src/` edits — `AcquisitionPolicy` still has per-technique flags; `--i-have-authorization` still exists; `SecurityFinding` still requires the full schema. All three are now *stale relative to the ADRs* and flagged in the backlog.
- No exploit actions built (ADR-16 decision). The ADR-12 bounded-business-intelligence bound is NOT lifted — user chose "only the exploit bound".
- Secrets rules untouched (non-overridable).
- README's "does not bypass authentication" left as-is — it remains accurate until exploit actions actually land.

## Why records-only is safe

The ADRs are the binding record for future agents ("respect these, don't relitigate"). Superseding them now means the *next* session that touches the security system reads the relaxed posture as the standing decision — code alignment becomes mechanical, not a re-litigation.

## Open items (see backlog)

- Align `src/` with ADR-15/16/17.
- Exploit actions: separate later decision (ADR-16 permits, builds nothing).
