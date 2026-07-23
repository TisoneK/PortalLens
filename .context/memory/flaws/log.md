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
