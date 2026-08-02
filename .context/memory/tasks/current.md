# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If a
prior session died mid-task, check its session entry and backlog first.

- **Session:** —
- **Task:** none — completed Session 14 (2026-08-02): refined the kickoff feature list (sections 1-5: bypass verification, gateway probing, parameter fuzzing, network mapping, intelligence gathering) against the existing ADRs. Plan-only — no `src/` commits. Six entries appended to `tasks/backlog.md` (CT-log framing stays as-is under the existing entry + the Session-12 footer; three new entries for passive/active additions; three per-action ADR-16 review items because the corresponding capabilities cross ADR-18's "never authenticate, submit credentials, send exploit payloads, or attempt to obtain access" boundary). One ADR drafted — ADR-19 session-replay classification — with two further per-action ADRs (default-credential auth, L2 MAC impersonation) flagged as **required before any code**, not drafted this session. Active-attack features will run behind the single `--authorized` flag (ADR-15) per the user's standing decision.
- **Status:** idle
