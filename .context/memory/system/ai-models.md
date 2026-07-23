# Agent + Model Registry (update in place)

Which agents and models have worked on this repo — and what they've
shown they can and can't do here. Update your row each session (last
seen + session count); add a row if you're new. The Observations
section is how the user learns which agent to hand which task, and how
agents learn a predecessor's blind spots (and verify its work
accordingly).

| Agent | Model | First seen | Last seen | Sessions |
|---|---|---|---|---|
| Super Z | unknown (GLM family) | 2026-07-23 | 2026-07-23 | 1 |
| Claude Code | claude-opus-4-8 | 2026-07-23 | 2026-07-23 | 1 |

## Observations

Concrete, evidence-based capabilities and limits — things demonstrated
in this repo's sessions, not marketing claims or self-assessment.
Update in place when a newer session contradicts an old observation.

- **Super Z / GLM family:** Bootstrapped `.context/` (core 0.2.0) on an empty PortalLens repo following `universal-kickoff.md` and `ai-engineering-protocol.md` — both the bootstrap step (Step 1a in the universal kickoff) and `context-sync verify` ran cleanly first try (2026-07-23)
- **Super Z / GLM family — blind spot:** shipped `relationship.py` emitting `USES_PLATFORM` and `AUTHENTICATES_FOR` **twice** for the same host pair, and it survived a CLI smoke test that the session-1 review recorded as "✅ Correct report produced". The output was read line by line for correctness but not scanned for duplicates across lines. Verify session-1 output for repetition, not just accuracy (found 2026-07-23, session 2)
- **Claude Code / claude-opus-4-8:** Reads the full protocol edition and follows Phase 1 before editing. Refactored the captive_wifi plugin from per-vendor branches to a declarative registry (ADR-5) while holding every confidence score identical — verified by rendering the report from the pre-refactor commit in a `git worktree` and diffing, rather than trusting the test suite alone. That diff is what caught the duplicate-relationship defect above. Test suite 55 → 80 (2026-07-23)
- **Claude Code / claude-opus-4-8 — note for the user:** interpreted a one-sentence chat target ("The portal is centered to a specific provider") as a statement about the *codebase* rather than the *analyzed portal*, and proceeded on that reading rather than asking, documenting the ambiguity in the review. If terse targets should trigger a question instead, say so once and it goes in `user/preferences.md` (2026-07-23)
