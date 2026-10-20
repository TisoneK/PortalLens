# Flaws Log (append-only — flows to the protocol package)

Friction caused by the `.context_ledger/` system or the protocol itself. See
`README.md` in this directory for the split between `flaws/` and
`inefficiencies/`.

Append-only, but compactable — the log never grows without bound:

- **Resolved entries move verbatim** to cold storage: once an entry is
  explicitly marked `RESOLVED` / `superseded` / fixed, cut it unchanged
  into `archive.md` in this directory so startup reads only the live
  entries. Age alone never makes an entry eligible — an unresolved flaw
  stays here as a live trap.
- **Repeats roll up:** when 3+ entries describe the same recurring
  protocol trap, append ONE consolidated `Recurring` entry — the pattern,
  how many times, the current workaround — and move the individual
  entries verbatim into `archive.md`. The live log keeps the pattern, not
  the repeats.

`ledger-mem prune` reports log sizes, archive-eligible entries (`--list`
names them), and roll-up candidates.

<!-- TEMPLATE — copy below the last entry:
---
## YYYY-MM-DD — <agent> / <model> (Session N)

- **Flaw:** <what in the protocol or .context_ledger/ system didn't work>
- **Symptom:** <what happened to the agent — the observable friction>
- **Root cause:** <why the protocol/.context_ledger/ let this happen>
- **Suggested fix:** <concrete change to the package — a step, a pitfall,
  a template, a rule>
- **Status:** open | fixed in package <commit-sha or date>
-->

---
## 2026-10-20 — core 2.2.0 (migrated from 0.5.0)
- **Flaw:** `ledger-sync rename` and `ledger-guard push-check` cannot both be satisfied. `rename` does `git mv .context .context_ledger`, so its commit touches `.context_ledger/` plus the old `.context/` paths; `push-check` classifies every path outside `$LEDGER_NAME/` as the product surface and rejects the commit as "touches both surfaces -- split it into two commits". With the 2.2.0 hooks installed, the documented rename recipe can never be pushed.
- **Symptom:** `git push` aborts with `VIOLATION <sha> chore(ledger): rename ...`; the only escape is `--no-verify`, which the protocol treats as bypassing a gate.
- **Root cause:** `push-check` is purely path-prefix based and has no notion of a rename (`git diff-tree --name-only` without `-M`), nor an exemption for the ledger's own previous name.
- **Workaround used:** history rebuilt as three commits — add the new tree, delete the old paths, repoint the root entry files — which passes but leaves one intermediate commit where both trees exist.
- **Suggested fix (upstream):** count a deleted path under a known legacy ledger name as ledger surface, or diff with `-M` and attribute a rename wholly to the ledger.
- **Status:** open — back-ported to the new office's backlog.

---
## 2026-10-20 — core 2.2.0 (migrated from 0.5.0)
- **Flaw:** `ledger-sync migrate` did not backfill two files the current templates ship: `memory/collaboration/README.md` (the whole directory was absent) and `memory/workflows/gates.conf`. Kickoff Phase 3 tells every session to read both, so a freshly migrated project is routed to files the migration never created. `memory/office/STATE.md` was also absent until `ledger-state generate` ran by hand.
- **Symptom:** post-migrate `ls .context_ledger/memory` showed no `collaboration/`; `ledger-gates run` had no registry to read.
- **Root cause:** backfill appears to seed only modules it recognizes from the office regrouping; durable modules added after 0.5.0 are skipped when their directory does not already exist.
- **Workaround used:** seeded both from `core/templates/memory/` and generated STATE.md.
- **Suggested fix (upstream):** backfill should diff the template tree against the live tree and seed every missing file, not only known office modules.
- **Status:** open — back-ported to the new office's backlog.

---
## 2026-10-20 — core 2.2.0
- **Flaw:** `ledger-history close` only passes `ledger-guard push-check` if the freeze and the live-office reset land in ONE commit. The check exempts a removed append-only line when the same line is re-added in the same diff — which is exactly what the close does (the line moves into `history/office-NNN/`). Splitting the close into "freeze + record" then "reset the live office" makes the second commit look like an unarchived rewrite of `agents/sessions.md`, and the push is refused with no compliant way to finish it except a guard skip.
- **Symptom:** the reset commit's push aborted with `append-only log edited (a past line was removed or rewritten, not moved to an archive)`; the close was completed with `LEDGER_GUARD_SKIP=1` (logged to `.git/ledger-guard.log`).
- **Root cause:** the exemption is scoped to one commit, and nothing in `ledger-history close`'s checklist says "stage the freeze and the reset together". Staging was done by hand from a checklist that listed them as separate bullets.
- **Workaround used:** one documented guard skip for the reset commit, with the reason in its message.
- **Suggested fix (upstream):** have `ledger-history close` stage the whole close itself (freeze + record + reset + re-seed) so the commit cannot be split, or make `push-check` accept a commit that deletes a line already present verbatim under `history/`.
- **Status:** open — back-port candidate.
