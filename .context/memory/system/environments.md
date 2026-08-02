# Environments (update in place)

Machines and sandboxes agents have run on, and what it takes to work on
this project from each. One block per environment; update the matching
block (and its "last verified" date) every time you run on it again.

## Rules

1. **Match before you add.** At session start, check whether the machine
   you're on already has a block (use its "Identify by" line). Update the
   match; add a new block only for a genuinely new environment.
2. **Record what you verified, not what you assume.** A command belongs
   under "Verified commands" only after it ran successfully on this
   environment, this project.
3. **Agents never delete blocks.** An environment the project no longer
   uses may be pruned by the user; if you can't verify a block, leave it
   alone — its last-verified date already says how stale it is.
4. **Machine facts only.** Secret values go in `secrets/`; user
   preferences in `user/`; project-wide decisions in `plans/`.

---
## Z.ai cloud sandbox (last verified 2026-07-23)
- **Identify by:** workspace path `/home/z/my-project/repos/`, session metadata `"channel": "zai-web"`, ephemeral container
- **OS:** Linux (Ubuntu-class sandbox)
- **Runtimes:** Python 3 (system), Node.js available
- **Package manager:** pip (Python); npm (Node, if needed)
- **Verified commands:**
  - `git clone` with PAT (private repos) — works, then `git remote set-url origin` strips the token
  - `sh .context/core/bin/context-sync bootstrap .` — vendored core 0.2.0 successfully
  - `sh .context/core/bin/context-sync verify` — passes (MANIFEST.sha256 matches)
  - Python `python3 -m venv .venv && pip install -e ".[dev]"` — the intended workflow (verify on first install)
- **Quirks:**
  - Ephemeral — `.context/memory/secrets/` does NOT persist across sessions; treat the `GIT_TOKEN` env var as the primary secret store
  - No persistent home directory — all work must live under `/home/z/my-project/`
  - System Python may be `externally-managed` — always use a `.venv` for project installs

---
## Tisone's macOS workstation (last verified 2026-08-02)
- **Identify by:** repo at `/Users/bao/Code/PortalLens`, Darwin 24.6.0 (macOS 15), local IDE agent (Claude Code), user's own git credentials
- **OS:** macOS 15 (Darwin 24.6.0), arm64
- **Runtimes:** system `python3` is **3.9.6** — below this project's `requires-python = ">=3.10"`, so it cannot run PortalLens. Use `/Users/bao/.local/bin/python3.12` (3.12.13). `uv` is also installed at `/Users/bao/.local/bin/uv`. No pyenv, no Homebrew Python on PATH.
- **Package manager:** pip inside a project `.venv`
- **Verified commands** (all run successfully on this machine, this project):
  - `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"` — creates the venv and installs dev deps
  - `.venv/bin/python -m pytest -q` — 146 passed (session 9; 80 in session 2)
  - `.venv/bin/ruff check .` — All checks passed
  - `.venv/bin/mypy src` — Success, 24 source files
  - `.venv/bin/portallens analyze "<url>" "<url>"` — renders the Markdown report on stdout (verified again session 9 on the real fixture pair)
  - `sh .context/core/bin/context-sync update` — core 0.3.0 → 0.5.0 applied cleanly (session 9); verify + status pass post-update
  - `git push origin main` — works with the user's existing credentials; no PAT involved (local agent)
- **Git identity:** repo-local `user.name`/`user.email` set to `Tisone Kironget <tisonkironget@gmail.com>` (the user's real, confirmed identity — see `user/identity.md`) on 2026-07-23. **Before this, NO identity was configured at any scope** (local + global both empty), so git auto-derived `Bao Le <bao@Baos-Mac-mini.local>` from this Mac's OS account — and sessions 2/3/5's commits went out under that name. (A brief intermediate fix set it to `Tisone K <...noreply>`, the stale bootstrap-recorded value; the user corrected it to the real identity.) If `git var GIT_AUTHOR_IDENT` ever shows `bao@Baos-Mac-mini.local` again, the local config was lost — re-run `git config --local user.name "Tisone Kironget" && git config --local user.email "tisonkironget@gmail.com"` (Step 1 of the local edition).
- **Quirks:**
  - **Reach for `python3.12`, never bare `python3`** — the bare one is 3.9 and will fail on this project's syntax and typing.
  - `.venv/` is gitignored; a fresh clone needs the venv step above before anything runs.
  - Session 13 verified `.venv/bin/ruff check src/portallens tests`, `.venv/bin/mypy src/portallens`, `.venv/bin/pytest -q` (220 passed), and `git diff --check`.
  - `git worktree add <path> <sha>` works and is a clean way to render "before" output for a refactor diff. Remove it with `git worktree remove <path>` when done.

---
## Tisone's Windows workstation (last verified 2026-07-23)
- **Identify by:** repo at `C:\Users\tison\Dev\PortalLens`, Windows 11, local IDE agent (GitHub Copilot), user's own git credentials
- **OS:** Windows 11 (10.0.22631)
- **Runtimes:** `C:\Python314\python.exe` (Python 3.14.2) is installed, but the project uses `.venv\Scripts\python` (3.14.2) inside the repo's venv at `C:\Users\tison\Dev\PortalLens\.venv\`
- **Package manager:** pip inside the project `.venv`
- **Verified commands** (all run successfully on this machine, this project):
  - `.venv\Scripts\python -m pytest -q` — 133 passed, 2 failed (pre-existing Windows path-separator issues in `test_xdg_data_home` + `test_default_under_home`)
  - `.venv\Scripts\ruff check .` — All checks passed
  - `.venv\Scripts\python -m mypy src` — Success: no issues found in 23 source files
  - `git push origin main` — works with the user's existing GitHub credentials (no PAT needed for local agent)
- **Quirks:**
  - Use `.venv\Scripts\python` (not bare `python` or `python3`) for all Python invocations
  - pytest path tests fail on Windows (POSIX path expectations). Pre-existing platform issue, not a regression
  - `context-sync` shell scripts need Git Bash at `C:\Program Files\Git\usr\bin\bash.exe` — verify/status/update may fail due to CRLF in MANIFEST.sha256 (see `memory/flaws/log.md`)
  - Windows paths use `\` — be careful with path constants in tests
  - No `context-sync verify` on this platform — use Python-based verification as fallback
