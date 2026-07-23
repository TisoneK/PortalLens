# Inefficiency Log (append-only, mandatory)

Every session appends one block — honestly. Friction you absorb silently
is friction the next agent hits blind. "None this session" is valid only
if literally nothing slowed you down.

---
## 2026-07-23 — Super Z / unknown (GLM family)
- **Problem:** Initial CLI draft used a convoluted monkey-patch for the `--i-have-authorization` flag — wrapper function + module-level `_confirmed_authorization` helper that was patched at call time. Hard to read, hard to extend.
- **Cost:** ~10 min spent writing the first version, then realizing it was unreadable, then rewriting it as a plain `is_flag` option.
- **Cause:** Trying to be clever with click's option composition instead of using the simplest possible form.
- **Workaround / fix:** Rewrote `cli.py` as a single `@click.command` with `--i-have-authorization` as a normal `is_flag=True` option, checked directly in the function body. Much cleaner.
- **Prevent next time:** Start with the simplest click form. Only reach for composition tricks when the simple form genuinely can't express what you need.

---
## 2026-07-23 — Super Z / unknown (GLM family) (2)
- **Problem:** First-pass relationship inference treated `link-orig` as a portal-redirect signal, producing false-positive "msftconnecttest.com redirects to captive.ispman.tech" inferences. `link-orig` is the URL the user was originally trying to reach (e.g. Apple's captive probe), not a portal redirect.
- **Cost:** ~15 min — caught by running the CLI on the real ISPMan URL pair, reading the output, identifying the false positive, then fixing the relationship inference to use only `link-login` / `link-login-only`.
- **Cause:** I read the MikroTik hotspot variable documentation too coarsely — `link-login`, `link-orig`, and `link-login-only` all sounded "redirect-shaped," so I lumped them together. Actually they have distinct semantics: `link-login` is the login page URL (back-reference), `link-orig` is the original destination the user tried to reach (not a portal URL at all).
- **Workaround / fix:** `relationship.py` now uses only `link-login` and `link-login-only` for redirect inference. `link-orig` is captured as evidence (the user might want to know what URL triggered the captive portal) but is not used for relationship inference.
- **Prevent next time:** When integrating with a foreign system's URL parameters, document each parameter's semantics in a comment at the point of use. Don't lump parameters by name-shape — lump them by behavior.

---
## 2026-07-23 — Super Z / unknown (GLM family) (3)
- **Problem:** First-pass fingerprint detection only ran on the primary URL. When the primary was `maz.wifi` (which only carries `dst` — the MikroTik entry signature), the analyzer missed the ISPMan fingerprint that lived on the other URL (`captive.ispman.tech`).
- **Cost:** ~10 min — caught by reading the first CLI output and noticing ISPMan wasn't in the fingerprint list.
- **Cause:** The analyzer's "pick first URL that looks captive as primary" logic was correct, but the subsequent "run fingerprints on primary only" step was a simplification that doesn't hold when the user supplies a URL pair.
- **Workaround / fix:** `analyzer.py` now runs `detect_fingerprints` for every supplied URL, dedupes by `(platform, version)`, and keeps the highest-confidence match.
- **Prevent next time:** When the user supplies multiple inputs, assume they're all relevant unless proven otherwise. "Optimize for the single-input case" is a frequent source of multi-input bugs.

---
## 2026-07-23 — Claude Code / claude-opus-4-8
- **Problem:** The project could not run at all on first try — this machine's `python3` is 3.9.6 and `pyproject.toml` requires `>=3.10`. No venv existed, and nothing in `.context/` said which interpreter to use, because the only recorded environment was an ephemeral Linux sandbox whose facts don't apply here.
- **Cost:** ~5 min hunting for a usable interpreter (`ls /opt/homebrew/bin/python3.*`, `command -v pyenv uv python3.12 …`) before finding `/Users/bao/.local/bin/python3.12`.
- **Cause:** `system/environments.md` had one block, for a cloud sandbox. A local agent on a different machine has nothing to match against and has to rediscover the toolchain. This is the per-machine scoping the protocol warns about (Pitfall #43) working as designed — the gap was simply that this machine had never been recorded.
- **Workaround / fix:** `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`. A full block for this machine is now in `system/environments.md`, including the explicit warning to reach for `python3.12` rather than bare `python3`.
- **Prevent next time:** Nothing to change in the protocol — the first agent on any new machine pays this cost once. The block now exists, so the next local session on this Mac shouldn't.

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (2)
- **Problem:** A green test suite is not evidence that a refactor preserved behaviour. All 55 tests passed on the first full run after the registry rewrite, while the rendered report still differed from the original in six places — including two duplicated relationships and a summary count of 6 where 4 was correct. The tests asserted *presence* (`assert uses_platform`) and never *count*, so a duplicate was invisible to them.
- **Cost:** None wasted — but it would have shipped a silent output change if the diff hadn't been run. The diff took ~4 min.
- **Cause:** The session-1 tests were written to assert that inferences exist, which is the natural shape for a first implementation. That shape cannot detect duplication or a changed score, which is exactly what a refactor threatens.
- **Workaround / fix:** `git worktree add <scratch> <pre-refactor-sha>`, render the same fixture through both trees with a 6-line script, `diff` the Markdown. Cheap, and it found a real bug in the *old* code (see review H-1). A `test_each_relationship_appears_once` regression test now exists.
- **Prevent next time:** For any refactor claiming "behaviour unchanged", diff the actual rendered output against a worktree of the base commit before committing. Do not accept a passing suite as the proof — say which one you ran (Pitfall #42 applies to "unchanged" claims as much as to "tests pass").

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (Session 3)
- **Problem:** None this session — appending ADRs and backlog items is friction-free with the templates in place. The one judgment call (how many ADRs to split the conversation into) resolved cleanly: seven atomic decisions, each constraining future agents differently, rather than one omnibus entry.
- **Cost:** negligible.
- **Cause:** n/a.
- **Workaround / fix:** n/a.
- **Prevent next time:** n/a — noting for honesty that a decisions-only session is where the `.context/` layout pays off most: there was an obvious, correct home for every decision.

---
## 2026-07-23 — Super Z / unknown (GLM family) (Session 4)
- **Problem:** The Z.ai cloud sandbox filesystem sets every file's mode to 100755 (executable), which made `git status` show ~20 tracked files as modified (mode-only changes, 0 insertions/deletions). I ran `git config core.fileMode false && git checkout -- .` to discard the mode changes — but `git checkout -- .` reverted the mode changes AND my real edits to `cli.py`, `pyproject.toml`, `README.md`, `CHANGELOG.md`, `docs/ARCHITECTURE.md`, and `tasks/current.md`. Only untracked new files (`src/portallens/tui/`, `tests/test_tui.py`) survived.
- **Cost:** ~15 min redoing the tracked-file edits. No data lost — the new TUI package was intact, and the edits were mechanical to re-apply (I had the content in conversation context).
- **Cause:** `git checkout -- <path>` discards ALL working-tree changes for that path, not just mode changes. `git config core.fileMode false` alone is enough to make `git status` ignore mode changes — the `checkout` was both unnecessary and destructive.
- **Workaround / fix:** Re-applied all the tracked-file edits. For the rest of the session, used `git config core.fileMode false` alone (set once, persisted for the repo) and never ran `git checkout -- .` again.
- **Prevent next time:** On the Z.ai sandbox (or any filesystem that flips file modes), run `git config core.fileMode false` once at session start. NEVER follow it with `git checkout -- .` — that discards real work. If mode changes are cluttering `git status`, `git config core.fileMode false` is the complete fix; no `checkout` needed.

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (Session 5)
- **Problem:** After `git pull` brought in session 4's changes (including an overwrite of `tasks/current.md`), the Read tool reported `current.md` as "unchanged since your last read" and refused to re-read — but the file HAD changed on disk via the pull. The harness's file-state cache tracks *my* reads/writes, not external mutations like a pull, so its "unchanged" claim was stale.
- **Cost:** ~2 min — I trusted the stale claim briefly, then confirmed the real content with `cat` before editing. No damage, because I verified rather than editing blind against the cached version.
- **Cause:** The file-state cache is invalidated by my own tool calls, not by `git pull` (or any out-of-band change). Right after a pull, every tracked file the pull touched can have a stale "unchanged" state.
- **Workaround / fix:** After a `git pull` that reports changed files, treat the file-state cache as stale for those files — re-read with `cat` (or Read, ignoring an "unchanged" note) before editing them. Editing produced a correct "the file had been modified on disk since you last read it" warning on one edit, which confirms the harness does detect it at write time — but the read-time "unchanged" claim is the trap.
- **Prevent next time:** Always `cat` a pulled-and-modified file before Editing it, regardless of what the Read cache says. This pairs with Pitfall #32 (don't inspect stale local state) — the same staleness applies to the harness's own file cache right after a pull.

---
## 2026-07-23 — GitHub Copilot / DeepSeek V4 Flash Free (Session 6)
- **Problem:** Two investigation-store path-resolution tests (`TestDbPathResolution::test_xdg_data_home`, `TestDbPathResolution::test_default_under_home`) assert POSIX `/`-separated paths and fail on Windows, which uses `\` separators.
- **Cost:** ~3 min identifying as pre-existing platform issue, not a regression.
- **Cause:** Tests written on macOS by Claude Code (session 5) with hardcoded POSIX path expectations (`"/xdg/portallens/investigations.db"`). The `resolve_db_path()` function correctly returns OS-native paths, but the tests compare against Unix paths.
- **Workaround / fix:** Use `os.path.join` or `Path(...)` operators in test assertions instead of hardcoded `/`-separated strings. E.g., `assert resolve_db_path(None) == Path("/xdg") / "portallens" / "investigations.db"`.
- **Prevent next time:** When writing path-assertion tests, use `os.path.join()` or `Path` operators rather than literal `/`-separated strings. This is equally portable and equally readable.

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (Session 5 addendum — git identity)
- **Problem:** Across sessions 2, 3, and 5 I committed as `Bao Le <bao@Baos-Mac-mini.local>` — an OS-auto-derived identity — instead of the project's recorded `Tisone K <TisoneK@users.noreply.github.com>`. This repo had NO git identity configured at any scope (local + global both empty), so git fabricated an author from the system account. The user noticed the two author names in the history ("I think local agent was also working").
- **Cost:** 14 commits already pushed to `main` under the wrong author name. Not rewritten (they're shared history; a force-push relabel is destructive and the user chose to leave them). Only future commits fixed.
- **Cause:** I skipped the local edition's **Step 1** git-identity check. Step 1 explicitly says: "If git identity is not configured (`git config user.name` returns empty), set it using the Pre-Flight values." `git config user.name` DID return empty — but commits succeeded (git auto-derives rather than erroring), so nothing forced me to notice. I never ran the check at session 2's start and it propagated silently across three sessions.
- **Workaround / fix:** `git config --local user.name "Tisone K" && git config --local user.email "TisoneK@users.noreply.github.com"` (user chose the project identity). Verified with `git var GIT_AUTHOR_IDENT`. Recorded on this machine's block in `system/environments.md` so the next local session starts from a known-good identity.
- **Prevent next time:** Run the Step-1 identity check at the START of every local session, and treat "commit succeeded" as NOT proof the identity is right — `git commit` never fails on an unconfigured identity, it fabricates one. Verify with `git var GIT_AUTHOR_IDENT` (not just `git config user.name`) before the first commit. The environments.md block now records the correct values for this machine.
