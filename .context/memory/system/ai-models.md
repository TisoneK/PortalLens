# Agent + Model Registry (update in place)

Which agents and models have worked on this repo — and what they've
shown they can and can't do here. Update your row each session (last
seen + session count); add a row if you're new. The Observations
section is how the user learns which agent to hand which task, and how
agents learn a predecessor's blind spots (and verify its work
accordingly).

| Agent | Model | First seen | Last seen | Sessions |
|---|---|---|---|---|
| Super Z | unknown (GLM family) | 2026-07-23 | 2026-07-23 | 2 |
| Claude Code | claude-opus-4-8 | 2026-07-23 | 2026-07-23 | 2 |
| GitHub Copilot | DeepSeek V4 Flash Free | 2026-07-23 | 2026-07-23 | 1 |
| Buffy | deepseek-v4-flash | 2026-08-01 | 2026-08-02 | 2 |

## Observations

Concrete, evidence-based capabilities and limits — things demonstrated
in this repo's sessions, not marketing claims or self-assessment.
Update in place when a newer session contradicts an old observation.

- **Super Z / GLM family:** Bootstrapped `.context/` (core 0.2.0) on an empty PortalLens repo following `universal-kickoff.md` and `ai-engineering-protocol.md` — both the bootstrap step (Step 1a in the universal kickoff) and `context-sync verify` ran cleanly first try (2026-07-23)
- **Super Z / GLM family — blind spot:** shipped `relationship.py` emitting `USES_PLATFORM` and `AUTHENTICATES_FOR` **twice** for the same host pair, and it survived a CLI smoke test that the session-1 review recorded as "✅ Correct report produced". The output was read line by line for correctness but not scanned for duplicates across lines. Verify session-1 output for repetition, not just accuracy (found 2026-07-23, session 2)
- **Super Z / GLM family — session 4:** implemented the ADR-7 TUI (Textual, responsive, optional extra) end-to-end including 22 async tests using Textual's `run_test` harness. Two first-pass bugs (Textual 8.x `Static.render()` must return `Text` not `str`; `confidence_markup` literal brackets needed escaping so `Text.from_markup` didn't parse the badge as a style tag) were caught immediately by the test suite, not by manual inspection — the async test harness paid for itself on the first run. ruff + mypy strict clean (2026-07-23)
- **Super Z / GLM family — session 4 blind spot:** ran `git checkout -- .` to discard spurious file-mode changes and accidentally reverted real edits to 6 tracked files. `git config core.fileMode false` alone was the correct fix; the `checkout` was destructive. Re-applied the edits from conversation context. See `inefficiencies/log.md` session-4 entry. (2026-07-23)
- **Claude Code / claude-opus-4-8:** Reads the full protocol edition and follows Phase 1 before editing. Refactored the captive_wifi plugin from per-vendor branches to a declarative registry (ADR-5) while holding every confidence score identical — verified by rendering the report from the pre-refactor commit in a `git worktree` and diffing, rather than trusting the test suite alone. That diff is what caught the duplicate-relationship defect above. Test suite 55 → 80 (2026-07-23)
- **Claude Code / claude-opus-4-8 — note for the user:** interpreted a one-sentence chat target ("The portal is centered to a specific provider") as a statement about the *codebase* rather than the *analyzed portal*, and proceeded on that reading rather than asking, documenting the ambiguity in the review. If terse targets should trigger a question instead, say so once and it goes in `user/preferences.md` (2026-07-23)
- **Claude Code / claude-opus-4-8 — session 5:** Implemented ADR-8 (persisted `Investigation`, SQLite) as directed, though it landed ahead of the ADR-9 ordering it had itself recommended — confirmed the two are independent before proceeding rather than reflexively following its own prior sequencing. Took "test real application" literally: exercised the built CLI across 4 separate processes against one DB file, not just in-process asserts. Document-in-SQLite + a real `PRAGMA user_version` migration ledger; derived the authorizable-technique set from `AcquisitionPolicy` so ADR-13's future flags need no edit. Tests 102 → 135, ruff+mypy clean (2026-07-23)
- **Buffy / deepseek-v4-flash — session 9:** setup-only session (core 0.3.0 → 0.5.0 sync + portallens initialization) — followed the full Phase 1 (pull, verify, read `.context/`, load local edition, baseline health) before any change; ran the code-reviewer on the `.context/` diff; completed the 0.5.0 exit including the new `memory/sessions/` module. Verified baseline green (ruff, mypy 24 files, 146 tests) and E2E CLI output on the real fixture pair (2026-08-01)
- **Buffy / deepseek-v4-flash — session 13:** implemented five bounded bypass probes and report-level detection; reviewer feedback caught and fixed parameter-tampering false negatives, stale test assumptions, and overclaiming from open ports. Final Ruff/mypy/pytest gates were clean (220 tests) (2026-08-02)
