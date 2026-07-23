# Flaws Log (append-only — flows to the protocol package)

Friction caused by the `.context/` system or the protocol itself. See
`README.md` in this directory for the split between `flaws/` and
`inefficiencies/`.

---
## 2026-07-23 — Super Z / unknown (GLM family) (Session 1)

- **Flaw:** The universal-kickoff's "Pre-Flight" section says the agent name + model + platform should be filled in by the user, but for a cloud/sandbox session started from a chat message (not a filled-in kickoff file), there's no clear path for the agent to record its identity. The protocol says "never guess your model version," but doesn't say what to do when the user hasn't supplied it AND the agent's system prompt doesn't state the exact model ID.
- **Symptom:** I had to record `unknown (GLM family)` as the model in `system/ai-models.md` and `agents/sessions.md`. That's better than a fabricated version number, but it's strictly less useful than a real version — the next agent reading the registry can't tell if I'm a 4.x or 5.x model.
- **Root cause:** The protocol assumes the kickoff file's Pre-Flight is the entry point, but cloud/sandbox sessions started from chat (like this one) bypass the kickoff file entirely. The agent has to back-fill identity from the chat context, which doesn't carry model version info.
- **Suggested fix:** Add a note to the protocol editions: "If you're a cloud/sandbox agent started from chat (no Pre-Flight supplied), record `unknown` for the model version in `system/ai-models.md` and `agents/sessions.md`. Note in your session entry that the model version was not supplied — the user can update it later by editing the entries in place." This is already what I did, but it would be reassuring to see it called out in the protocol.
- **Status:** open

---
## 2026-07-23 — Super Z / unknown (GLM family) (Session 1) (2)

- **Flaw:** The bootstrap step (`sh ../context/core/bin/context-sync bootstrap .`) produces a `.context/memory/` skeleton where every memory file has a HTML-comment template at the top explaining what to fill in. Good. But the template doesn't make it obvious that the bootstrap agent is expected to fill these in *in the same commit* as the bootstrap itself. I read the universal-kickoff.md carefully and saw the instruction in Step 1b, but a less-careful agent might commit the bootstrap with empty memory files and then have to backfill.
- **Symptom:** I caught this only because I'd read the universal-kickoff.md in full before running the bootstrapper. A faster-moving agent might have shipped an empty-memory bootstrap.
- **Root cause:** The `context-sync bootstrap` command's "next steps" output says "fill .context/kickoff.md Project Facts + AGENTS.md <PROJECT_NAME>" and "fill memory/..." but doesn't emphasize that these go in the SAME commit as the bootstrap.
- **Suggested fix:** Add a line to the bootstrapper's "next steps" output: "Commit these together with the bootstrap as one `chore(context): bootstrap .context/` commit — do NOT push an empty-memory bootstrap." The universal-kickoff.md already says this in Step 1d, but the bootstrapper's stdout is what an agent actually reads.
- **Status:** open

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (Session 2)

- **Flaw:** Three protocol rules give conflicting direction when the session's Target is free text that is *itself* an architectural change. Step 9 says "Free text — interpret the target; if ambiguous, ask once in chat before proceeding." The Findings-handling parameter says "flag architectural changes for explicit approval." But the Zero-Interruption Principle and Pitfall #30 both say not to stop and ask. This session's target — "The portal is centered to a specific provider" — was ambiguous (a statement about the analyzed portal, or about the codebase?) *and* implied an architectural change, so all three rules were live at once and pointed different ways.
- **Symptom:** Real deliberation about whether to spend a turn asking or to proceed. Resolved by proceeding on the stronger reading and documenting the ambiguity prominently — in the review's "Target interpretation" section, in the session entry, and in the chat summary — so the user can redirect cheaply. But the protocol did not direct that choice; it was made in spite of the protocol, which the Session Lifecycle section says is a failure ("If you don't know what to do next, the protocol has failed").
- **Root cause:** The three rules were written for different situations and never reconciled. "Flag architectural changes for approval" assumes the architectural change is something the agent *discovered*, not something the user *asked for*. A user-supplied target is already the user's authorization for the change it names — but the protocol doesn't say that anywhere, so the finding-handling rule appears to apply to it.
- **Suggested fix:** Add to the Findings-handling parameter and to Step 10: "A Target the user supplied IS approval for the architectural change it describes — the flag-for-approval rule governs changes you discovered, not the one you were asked for." And to Step 9's free-text clause: "If a reading is well-supported by the code and the alternative describes work already shipped, take the supported reading, state the assumption in the report and chat summary, and keep the work additive so a different reading can be taken from the same base — don't spend a turn asking."
- **Status:** open

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (Session 2) (2)

- **Flaw:** Step 3 says to set `.context/memory/tasks/current.md` "before starting work" and lists it as the last bullet of Step 3 — i.e. before Step 4 (install), Step 5 (read docs), Step 7 (discovery), and Step 8 (baseline). When the Target is free text, the task cannot be stated accurately until *after* that exploration: this session could not have written a useful `current.md` entry before reading the source, because the entry's content ("ISPMan is hardcoded across four modules") *was* the finding of Phase 1.
- **Symptom:** `current.md` was written after Step 8 rather than at Step 3. The session lock — whose purpose is to stop a second agent starting concurrently — was therefore absent for the whole of Phase 1, the longest read-only stretch of the session.
- **Root cause:** `current.md` serves two purposes that want different timings: it is a **lock** (wants to be set as early as possible, needs no detail) and a **task record** (wants detail, so needs Phase 1 done). The protocol treats them as one write.
- **Suggested fix:** Split the write in the editions. At Step 3: "Claim the lock — write `current.md` with the session id and the raw Target verbatim, even if you can't yet describe the work." At the end of Step 8: "Refine `current.md` with what Phase 1 established about the task." One sentence each; makes the lock cover Phase 1, which is where a colliding agent does the most redundant work.
- **Status:** open

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (Session 2) (3)

- **Flaw:** Pitfall #41 says "Don't write dates from memory — run `date -u +%F`." It doesn't cover the case where the agent's harness *supplies* a date in its context that disagrees with the command. Here the harness context stated 2026-07-22 while `date -u +%F` returned 2026-07-23 (the machine's local clock was late on 07-22; UTC had rolled over).
- **Symptom:** Two plausible dates for an append-only entry, one of which would have made this session appear to precede session 1 (dated 2026-07-23) in a log whose whole value is chronological ordering. Resolved by following the command, which also matches the user's timezone (Africa/Nairobi, UTC+3, per `user/identity.md`), but the protocol only implies this rather than saying it.
- **Root cause:** Pitfall #41 addresses the model fabricating a date. It doesn't anticipate a *harness-supplied* date, which doesn't feel like "from memory" and so doesn't obviously fall under the rule — while being just as capable of being stale or in a different timezone.
- **Suggested fix:** Extend Pitfall #41: "This includes a date supplied by your harness or system context — it may be stale or in a different timezone than the repo's history. `date -u +%F` is the only authority. If the two disagree, use the command and note the discrepancy in your session entry so the next agent doesn't churn on it."
- **Status:** open

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (Session 2) (4) — CORRECTION to entry (1) above

- **Correcting:** the first Session 2 entry, which claimed Step 9 ("Free text — interpret the target; if ambiguous, ask once in chat") conflicts with the Zero-Interruption Principle and Pitfall #30 ("don't ask permission"). **That claim is wrong and the suggested fix for it should not be harvested.**
- **Why it's wrong:** the two rules govern different acts. Pitfall #30 prohibits *rhetorical permission questions* — the ones that need only a "yes" or "go ahead" for something the protocol already prescribes ("Want me to commit?", "Should I fix this or log it?"). Step 9 concerns *genuine ambiguity of meaning* — where the agent cannot tell what was asked for. Asking the second kind was never prohibited. Pitfall #30 states this boundary in its own closing sentence ("it does NOT prohibit asking for a **missing input** only the user can supply… a decision between two valid architectures"); the original entry missed it. The user confirmed this reading directly (2026-07-23).
- **What still stands from entry (1):** only the narrower point about the Findings-handling parameter. "Flag architectural changes for explicit approval" reads as though it covers an architectural change the *user asked for* in the Target, when it is plainly meant for changes the agent *discovered*. A Target the user supplied is already approval for the change it names. That one sentence is still worth adding to the editions; the Step 9 / Pitfall #30 half of the suggested fix is withdrawn.
- **What this session should have done:** this target ("The portal is centered to a specific provider") was genuinely ambiguous, so Step 9 applied and asking would have been legitimate — no rule stood in the way. Proceeding on the well-supported reading also turned out to be what the user wanted, but that was the right call on its merits, not a rule conflict resolved under duress.
- **Lesson for the next agent:** before logging a protocol conflict, re-read both rules in full — including their closing qualifiers. `flaws/` flows upstream to the package (core 0.3.0 `context-sync harvest`), so a misread rule becomes a proposed change to every project on the protocol. Cost of a wrong flaw entry is paid fleet-wide, not locally.
- **Status:** this correction closes the Step 9 / Pitfall #30 claim in entry (1) as **invalid — do not harvest**. The Findings-handling point remains open.

---
## 2026-07-23 — GitHub Copilot (Session 6)

- **Flaw:** `context-sync verify` fails on Windows Git Bash because `sha256sum` reads MANIFEST.sha256 with CRLF line endings, causing file paths in the manifest to carry a trailing `\r` (shown as `$'\r'`), so they never match actual on-disk filenames. `context-sync rollback` works correctly (it restores from git history and updates `core.lock`), but the subsequent `verify` always fails on Windows regardless of actual core integrity.
- **Symptom:** Every `context-sync verify` invocation on Windows reports "CORE INTEGRITY FAILURE" even though the core was just rolled back from a known-good git commit. The agent cannot confirm core integrity using the vendored tool, which blocks the protocol step that says "verify cleanly or rollback and log."
- **Root cause:** `context-sync` was authored for POSIX systems (macOS/Linux) where `sha256sum` expects LF-delimited input. On Windows, Git's `core.autocrlf` converts the manifest to CRLF, and `sha256sum` includes the `\r` in the file path, making lookup fail. The script uses `set -u` and `$(sha_cmd) --check --status MANIFEST.sha256` with no CRLF sanitization.
- **Suggested fix:** Add CRLF normalization in `context-sync verify` — run `sed -i 's/\r$//' "$CORE_DIR/MANIFEST.sha256"` (or a portable equivalent) before invoking `sha256sum`, or document in the protocol editions that on Windows the agent should use Python to verify checksums when the shell script fails due to CRLF. The `rollback` and `lock` commands work fine; only `verify` is affected.
- **Status:** open
