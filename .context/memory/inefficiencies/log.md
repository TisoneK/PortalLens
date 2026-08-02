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

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (Session 7)
- **Problem:** None that cost time. Worth noting for the next agent: changing a widely-consumed field's type (`open_questions: list[str]` → `list[OpenQuestion]`) went smoothly because a single upfront `grep -rn "open_questions\|OpenQuestion" src tests` mapped every consumer (analyzer, Markdown renderer, TUI panel, CLI count, three test files) before any edit. Nothing was missed; the first full test run was green.
- **Cost:** negligible.
- **Cause:** n/a.
- **Workaround / fix:** n/a.
- **Prevent next time:** When changing a model field's type, grep every reference first and migrate all consumers in one pass. The TUI (an optional-extra consumer) is the easy one to forget — it broke in no way only because the grep caught `tui/widgets.py`.

---
## 2026-07-23 — GitHub Copilot / DeepSeek V4 Flash Free (Session 8)
- **Problem:** `portallens show <id>` crashes on Windows with `UnicodeEncodeError: 'charmap' codec can't encode character '\u2265'`. The report renderer in `reporting/__init__.py` uses Unicode characters (`≥` for ranges, `—` for em-dashes, `–` for en-dashes, `…` for ellipsis) that aren't in the Windows cp1252 code page. `click.echo()` writes to stdout via `sys.stdout.write()`, which on Windows uses the console's active code page (typically cp1252 for Western European locales).
- **Cost:** ~5 min — discovered by running `show` on the saved investigation after `investigate` + `investigations` both worked. Root-caused by checking the stack trace, identifying all non-ASCII chars in the renderer, and replacing them with ASCII-safe alternatives (`>=`, `-`, `...`).
- **Cause:** The report renderer was authored on macOS/Linux where UTF-8 is the default encoding. Unicode chars render fine there. Windows defaults to a legacy code page (cp1252) for stdout, which cannot encode U+2265 and friends. No `encoding="utf-8"` override or stream wrapper was in place.
- **Workaround / fix:** Replaced all non-ASCII chars with ASCII equivalents in `src/portallens/reporting/__init__.py`:
  - `≥` → `>=` (range prefix)
  - `—` → `-` (em-dash separators in table cells and prose)
  - `–` → `-` (en-dash in range "0–19" → "0-19")
  - `···` → `...` (ellipsis in redact)
- **Second-wave issue:** After rebasing onto the concurrent ADR-9 commit (macOS agent), the first fix pass had missed em dashes the ADR-9 changes re-introduced in the same renderer. Required a second fix pass (`75d7854`). Lesson: when merging concurrent branches that both touch output formatting, diff the rendered output against the pre-merge base.\n- **Prevent next time:** When writing output that goes through `click.echo()` (which writes to `sys.stdout`), stick to ASCII printable chars unless the code explicitly sets `sys.stdout.reconfigure(encoding="utf-8")`. This is especially relevant for cross-platform libraries where macOS/Linux devs won't notice the bug. A project-wide linter rule (e.g. Ruff's `RUF001`/`RUF002`/`RUF003` — already in the config as ignored) could catch non-ASCII in format strings if re-enabled for the reporting module. Also: after any rebase/merge, run the app on Windows (or grep for non-ASCII in format strings) to catch regressions.

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (Session 7 addendum — cp1252)
- **Problem:** Session 8 (Copilot/Windows) fixed "Windows cp1252" report breakage by replacing em dashes (—) and ellipsis (…) with ASCII — but those characters are actually IN cp1252, so they were never the breaker. The character that genuinely raises `UnicodeEncodeError` on a cp1252 stdout is the `->` arrow (U+2192) used in relationship values like `maz.wifi -> captive.ispman.tech`. So the report could still break on Windows for any input that produces a redirect/uses-platform/authenticates-for relationship (i.e. the normal case).
- **Cost:** ~5 min — found only because I did `md.encode("cp1252")` on the actual rendered report rather than eyeballing which characters "looked non-ASCII". The encode call pinpointed U+2192 at an exact offset.
- **Cause:** The Session-8 fix targeted characters that look exotic (em dash, ellipsis) instead of testing which characters actually fail to encode. Middle dot (·, U+00B7) and em dash (—, U+2014) are both in cp1252; the arrow (→, U+2192) is not.
- **Workaround / fix:** Replaced the three emitted `other=` arrows in `relationship.py` with `->`, the observation middle dot in `reporting/` with `|`, and two strays in `cli.py`. Verified the whole rendered report + CLI output `.encode("cp1252")` cleanly. Commit cc07f0b.
- **Prevent next time:** To make output encoding-safe for a target codepage, don't guess by eye — round-trip the actual emitted string through `.encode("<codepage>")` and fix exactly what raises. TUI output (`tui/theme.py`, `tui/widgets.py`) still uses `·`/`→` but goes through Textual's own driver (a different path), so it was intentionally left; if a Windows TUI encoding issue surfaces, that's the next place to apply the same encode-test method.

---
## 2026-07-23 — Claude Code / claude-opus-4-8 (Session 7 addendum 2 — encoding boundary)
- **Problem:** Both Session 8's cp1252 fix AND my follow-up (cc07f0b) sanitized *source strings* character-by-character. The user pointed out the right question: "Can't a function handle them?" It can and must — because the report prints **user-supplied data** (URLs, query-param values become evidence), so an IDN host or a percent-decoded Unicode param reaches stdout regardless of how clean the source strings are. Source sanitizing is not just tedious, it's incomplete by construction.
- **Cost:** Two prior commits (Session 8's + cc07f0b) spent on a symptom-level approach before the boundary fix landed.
- **Cause:** Treating an output-encoding problem as a content problem. The character that fails to encode can originate from input, so it can't be fixed where the static text is written — only where text is emitted.
- **Workaround / fix:** `portallens/output.py::console_safe(text, encoding)` + `echo()` — encode-test at the single emit boundary, degrade only what the target console can't take (known glyphs -> ASCII stand-ins, catch-all replace for the rest). CLI routes every emit through `echo()`. Commit 2bc6872. The earlier source ASCII edits are now belt-and-suspenders; they can be reverted to nicer Unicode once the concurrent session finishes editing reporting/__init__.py.
- **Prevent next time:** Encoding/escaping/redaction of *output* belongs at the output boundary, applied to the final string — not scattered across the code that builds it. If output can contain user input (it usually can), the boundary is the ONLY complete place. This generalizes: the same is true of the TUI's rich-markup escaping and the report's secret redaction.

---
## 2026-08-01 — Buffy / deepseek-v4-flash (Session 9)
- **Problem:** `agents/sessions.md` contains **two** entries both labelled "Session 8" — two concurrent Windows agents (GitHub Copilot) logged the same day, each numbering itself 8. This session had to be 9, but anyone citing "session 8" from now on must disambiguate by commit range or machine. Minor, but it will keep recurring while the numbering is manual.
- **Cost:** ~2 min — noticed during Step 3 reading; noted in the session entry and report rather than editing (append-only).
- **Cause:** The protocol has no session-number allocation mechanism; two sessions on the same repo same-day both read "last was 7" and both claimed 8. Nothing in `.context/` prevented it.
- **Workaround / fix:** Recorded this session as 9 and flagged the ambiguity; next agents should cite commit SHAs when referencing "session 8". The 0.5.0 `memory/sessions/` module's SUMMARY.md gives a cleaner continuity view for future numbering.
- **Prevent next time:** When starting a session, count actual entries in `agents/sessions.md` (not the last visible number) before numbering, and cross-check against the most recent date. Worth a flaw entry if it recurs.
- **Also noted:** `context-sync.ps1` (core 0.4.0/0.5.0) has never been exercised by a real Windows agent — the next Windows session should run it and log the result; the sh-based `verify` is known to break on Windows Git Bash CRLF (logged flaw, session 6).

---
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 11)
- **Problem:** The kickoff target "Remove any .context constraints that feel restrictive. The project should stay flexible." was ambiguous between *workflow ceremony* (push policy, report requirements, Phase-1 steps) and *security constraints* (ADR-1/10/12/13, acquisition policy, disclosure schema). My first ask_user round presented workflow-ceremony options; the user interrupted with "I meant security constraints". Additionally, the first ask_user's second question (change scope) returned with no answer selected, so it had to be re-asked in a second round.
- **Cost:** ~2 ask_user rounds before any edit; zero time wasted on edits since the user stopped me before I touched anything.
- **Cause:** The word "constraints" legitimately spans both surfaces; I guessed the workflow reading first. And the multi-question ask_user response came back with only Q1 answered — the scope question silently lacked an answer.
- **Workaround / fix:** Re-scoped to security constraints, then re-asked the scope question alone; the user's answers collapsed the task to "lift the ban, build nothing, records-only".
- **Prevent next time:** For an ambiguous target spanning workflow vs. project policy, present a *category* question first ("which kind of constraints?") before detailed options. After a multi-question ask_user, verify every question got an answer before proceeding.

---
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 12)
- **Problem:** Two str_replace attempts on `cli.py` missed on exact-match because my oldString over-escaped quotes inside a triple-quoted docstring (`\"` instead of `"`). Same class of miss hit the `tui` command block on the first pass — the fixes landed only after re-reading the file and matching the real characters.
- **Cost:** ~3 read/replace rounds per miss instead of one.
- **Cause:** Copying a docstring from the conversation where quotes had been JSON-escaped, then re-escaping them again in the replacement payload.
- **Workaround / fix:** Re-read the file and build oldString from the file's literal content (plain `"`, not `\"`).
- **Prevent next time:** When the oldString spans a docstring, verify quote escaping against the actual file bytes before replacing — or split the replacement to avoid the quoted span entirely.
- **Also noted:** the `code-searcher` agent returned no output once when spawned with a malformed params object (missing `searchQueries`); re-spawning with the full params object fixed it. And a first validation basher failed with "command not found" for ruff/mypy/python because it didn't source `.venv/bin/activate` — the environment block in `system/environments.md` already records that the tools live in `.venv`, so sourcing the venv first is the standing fix.

---
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 13)
- **Problem:** Exact-string edits to the new parameter-tampering test/probe briefly produced a syntax collision and stale fixture assumptions; URL query encoding also hid the injected sentinel from the test callback.
- **Cost:** Several focused reruns and one final full-suite rerun.
- **Cause:** The mutation helper correctly percent-encodes the sentinel, while the test callback initially searched the raw URL; one replacement joined a declaration and loop on the same line.
- **Workaround / fix:** Re-read the actual file, used URL decoding in the injected test request, added a default-sentinel regression, and reran Ruff, strict mypy, full pytest, and `git diff --check`.
- **Prevent next time:** When testing URL mutations, inspect decoded query values rather than raw serialized URLs; after chained exact replacements, run syntax/lint immediately before broader tests.

--
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 14)
- **Problem:** First-pass `str_replace` to append six backlog items to `tasks/backlog.md` mistakenly re-listed the two Session-13 entries ("CLI/investigation orchestration for bypass probes" and "Calibrate bypass verification") at the bottom of the new block, marked *(session-13 entry, kept)*. File momentarily contained sentence-for-sentence duplicates of items already present at the top of my `oldString` anchor.
- **Cost:** One extra `str_replace` to scrub the duplicates; otherwise no impact (caught before commit).
- **Cause:** I was treating append-only as "append + optional re-list of older items for emphasis", which was neither needed nor useful; the originals stand by themselves and adding placeholders like *(kept)* duplicates them visually.
- **Workaround / fix:** Targeted the duplicated tail block with a single `str_replace` and removed the two extraneous entries. The new Session-14 additions stand on their own; no re-listing of older items.
- **Prevent next time:** When appending to an append-only file with a known tail, anchor on the **last** existing item and append only the new entries — do not include older items in the new content. "Kept" placeholders for unmodified older entries are noise; anything that needs to be referenced aloud belongs in the *current* entry's prose.

--
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 14 (2))
- **Problem:** `read_files` (and the thinker's `read_files`) was truncated by the harness's 20,000-token ceiling whenever I asked for several large `.context/memory/` files in one call. Files like `agents/sessions.md` and `plans/decisions.md` came back with the last ~30% cut off, forcing me to re-read individually or piece content from earlier calls.
- **Cost:** ~3 extra read calls across the session; no functional impact because both me and the thinker had enough from the partial reads.
- **Cause:** I bundled too many large files into single `read_files` calls; the per-call token cap truncates rather than errors.
- **Workaround / fix:** When context density is the goal, prefer smaller targeted calls or have the thinker handle the heavy reads. Worked around here because I had prior partial reads.
- **Prevent next time:** For `.context/memory/` reads, prefer two or three smaller `read_files` calls over one big one, or pass a single large file plus context to the thinker and let it budget internally.

--
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 14 (3))
- **Problem:** Session 13's review report flagged 17 pre-existing `mypy --strict` errors in `tests/test_tui.py` + `tests/test_bypass.py` (and 3 other files). Session 14 (plan-only) explicitly deferred this rather than addressing it: touching `tests/` was outside the plan-only scope.
- **Cost:** Zero this session — `pytest` still passes 220 with the test-mode relaxations standing; the `workflows/active.md` "ruff + mypy strict clean" expectation is already red from Session 13. Carried-over debt, not new friction.
- **Cause:** Session 13 landed `bypass_detection.py` and new probe tests without a `mypy --strict src tests` pass on the new code. The drift came in with that product commit, not as a later regression.
- **Workaround / fix:** Logged as research item **R3** in `.context/memory/sessions/2026-08-02-14/research-questions.md` — research-priority lowest, mechanical fix in any session. Concrete locations: `tests/test_tui.py:228` (missing type annotation), `tests/test_bypass.py:194/224/238` (`portal_type: str` passed where `PortalType` enum expected; the remaining 13 errors are spread across 3 other files and need a fresh `mypy --strict src tests` to enumerate precisely).
- **Prevent next time:** Add a `mypy --strict src tests` pre-commit (or pre-PR) check so the standing expectation in `workflows/active.md` cannot drift from session to session. If strict is too noisy for daily work, decide explicitly to relax it — do not let it lag silently.

--
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 14 (4) — relocation)
- **Note:** The previous Session-14 (3) entry (the mypy-strict baseline deferral note) was filed here in error. `inefficiencies/log.md` is for friction *experienced this session*; the mypy entry is "carried-over debt from Session 13" — that fits `flaws/log.md`'s standing-debt convention better. The canonical mypy-deferral tracking has been re-filed in `.context/memory/flaws/log.md` (the latest entry there). This Session-14 (4) entry is the append-only correction so the trail isn't split.
- **Decision:** subsequent sessions logging standing-debt items should put them in `flaws/log.md` directly. Honest-friction entries in this file should reference *what slowed work this session*, not deferred follow-ups.
- **Cost:** one extra commit, one file duplication. No functional impact.
- **Cause:** the Session-14 (3) wording ("carried-over debt, not new friction") did not match the file header ("Friction you absorb silently"). The standing append-only convention precludes fix-in-place, so re-file + correction-note is the right shape.

--
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 15)
- **Problem:** The first `portallens --help` smoke check failed with "command not found" — the CLI is installed in the project `.venv` but the shell had no activated venv. Also re-hit the known `read_files` 20k-token truncation (Session-14 (2)) when batching several large `.context/memory/` files in one call.
- **Cost:** ~2 min — one extra basher call to find `.venv/bin/portallens`; one re-read batch for the memory files.
- **Cause:** `portallens` is not on PATH without `source .venv/bin/activate`; the harness read-truncation cap on bundled large files is the known Session-14 (2) trap.
- **Workaround / fix:** Used `.venv/bin/portallens` directly; kept `.context/` reads to smaller targeted batches.
- **Prevent next time:** `system/environments.md` already records `.venv/bin/...` as the verified invocation forms for this machine — check that block before running any project CLI rather than guessing bare names (this session did exactly that in hindsight; the block was read later).

## 2026-08-02 — Buffy / deepseek-v4-flash (Session 16)
- **Problem:** Three tooling friction points while building the live TUI console. (1) The `tmux-cli` agent failed to start — this machine has no `tmux` binary, so a PTY driver had to be found (`expect`). (2) The first attempt to drive the TUI via an inline `expect` heredoc was rejected by the spawn tool (JSON nesting too deep for a long quoted command) — the script had to be written as a real file first. (3) Repeated `str_replace` anchor failures on `docs/TUTORIAL.md` — the file contains literal backslash-escaped quotes from earlier edits, so quote-heavy anchors never matched (4 failed attempts).
- **Cost:** ~6-8 min total.
- **Cause:** (1) tmux not installed on this workstation (only `expect` is available). (2) Very long inline heredocs with nested quotes don't survive the spawn-tool JSON layer. (3) Quote-heavy anchor strings are brittle in str_replace when the file itself contains escaped quotes.
- **Workaround / fix:** (1) Verified available PTY drivers with `which tmux/script/expect`, then used `expect` + a script file. (2) `write_file` the expect script, then run it in a separate basher call. (3) Fell back to `.venv/bin/python - <<'PYEOF'` heredoc edits with `assert old in s` — atomic, escaping-proof.
- **Prevent next time:** Check `which tmux` before spawning tmux-cli; without tmux, go straight to expect-with-script-file. For quote-heavy doc edits, use Python-heredoc string edits from the start. Also: `App._log` collides with Textual's internal logger — check helper-method names against parent-class privates when subclassing framework apps (the TUI test suite caught this immediately).

---
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 17 repair)
- **Problem:** The first context commit accidentally rewrote four append-only files (`agents/sessions.md`, `inefficiencies/log.md`, `sessions/SUMMARY.md`, and `tasks/backlog.md`) instead of appending, and the bad commit was pushed before the deletion was noticed.
- **Cost:** One corrective context commit and an additional verification pass; product code was unaffected.
- **Cause:** Whole-file writes were used for append-only files despite the protocol's append-only rule. The staged diff showed hundreds of deletions, but the first commit command did not stop on that review signal.
- **Workaround / fix:** Restored the four files from the true pre-session baseline `bb94df4`, re-appended their Session 17 entries with shell append operations, and will push the repair as a separate context commit.
- **Prevent next time:** Never use `write_file` on append-only context files. Before committing context, require `git diff --cached --numstat` to show zero deletions for append-only paths and abort if any deletion appears.

---
## 2026-08-02 — Buffy / Session 18
- **Problem:** An attempted append to the append-only ADR file used the file-write operation and replaced the prior decision history instead of appending. A syntax cleanup also briefly joined an import block to the following constant in a test file.
- **Cost:** ~10 min restoring `plans/decisions.md` from the shipped product commit, re-appending ADR-21 with shell redirection, and repairing the test syntax before final gates.
- **Cause:** Used a whole-file writer for an append-only context file and applied a replacement against text that had already changed.
- **Workaround / fix:** Restored from `fb99e47`, used `cat >>` with a heredoc, verified ADR-20 remained and `git diff --numstat` showed 7 additions / 0 deletions; repaired the import separator and reran all gates.
- **Prevent next time:** Treat append-only context files as shell-append-only. Before any append, anchor from the file tail; after appending, compare against the pre-session baseline and require zero deletions.

---
## 2026-08-02 — Buffy / Session 19
- **Problem:** The first picker controller draft exposed two integration issues: Textual callbacks arrived before the worker was scheduled in the test harness, and the picker mutated a private controller listener. Review also found stale rows visible during rescan and a Python-3.10 `typing.Self` incompatibility.
- **Cost:** ~20 min running focused diagnostics, checking Textual callback APIs, and tightening the controller/picker boundary before the full suite.
- **Cause:** The initial design assumed worker callback timing and treated the presentation callback as an internal implementation detail.
- **Workaround / fix:** Added explicit listener registration, main-thread-aware callback delivery with shutdown tolerance, public initial-state seam, stale-row clearing, generation guards, and a Python-3.10-compatible forward-reference return annotation. Full validation was rerun after each correction.
- **Prevent next time:** Test Textual worker timing separately from pure controller timing; keep UI callback registration public and lifecycle-aware from the first draft.

---
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 20)
- **Problem:** The tool harness surfaced repeated unavailable `set_output`/agent-tool errors in the inherited conversation and required several review/test iterations to converge on import ordering and calibrated probe semantics.
- **Cost:** Moderate iteration overhead; no product data or code was lost.
- **Cause:** Historical tool-call errors were carried into the resumed turn, and review correctly exposed edge cases (SSRF through arbitrary profiles, overclassification of HTTP errors, state idempotency, and content-type/provenance gaps) after the first implementation.
- **Workaround / fix:** Continued with available tools, used deterministic injected HTTP seams, applied reviewer findings before the final gate, and verified the full suite after each correction.
- **Prevent next time:** Treat resumed historical tool errors as non-authoritative noise; run a security-focused review immediately after the first detector draft and keep caller-provenance assertions explicit in the API.

---
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 21)
- **Problem:** Two append-only context files were initially edited with whole-file writes during the interrupted continuation, which risked losing prior session history; one decisions-file replacement also needed recovery.
- **Cost:** Several repair/read cycles before committing context; no prior history was lost because each file was restored from `HEAD` before append.
- **Cause:** Using the file-write tool for append-only logs instead of restoring and appending with a shell redirection.
- **Workaround / fix:** Restored `agents/sessions.md`, `sessions/SUMMARY.md`, `inefficiencies/log.md`, and `plans/decisions.md` from `HEAD`, then appended only the new entries with `cat >>`. Verified tails and diff hygiene.
- **Prevent next time:** Never use whole-file write tools on append-only context files. Use `git show HEAD:file > file` only for recovery, then append with `cat >>`.

---
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 22)
- **Problem:** Textual's asynchronous ListView mounting made fast repeated rescans timing-sensitive, and the first keyboard regression test did not actually focus the list. Review also identified blocking Event waits inside async tests.
- **Cost:** Several focused test and harness iterations; no shipped regression.
- **Cause:** The original renderer treated every generation as a reason to rebuild the DOM, while Textual queues child mounts. Test input focus was assumed rather than made explicit.
- **Workaround / fix:** Compared stable rendered-row signatures, kept rows during scans while disabling stale interaction, skipped UI rescans during active scans, explicitly focused ListViews, and replaced blocking waits with non-blocking pilot polling. Controlled harness and full suite confirmed repeated scans retain one row and timers stop on unmount.
- **Prevent next time:** For Textual list tests, explicitly focus the list before keyboard input; never block the event loop waiting for worker events; treat asynchronous child mounting as a DOM lifecycle boundary and avoid unnecessary clear/rebuild operations.
