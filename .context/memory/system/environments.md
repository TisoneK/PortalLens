# Environments (update in place)

Machines and sandboxes agents have run on, and what it takes to work
on this project from each. One block per environment; update the
matching block (and its "Identify by" line) every time you run on it
again.

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
- **Verified commands (Session 17, 2026-08-02):**
  - `source .venv/bin/activate && pytest -q tests/test_wifi.py` — 14 passed
  - `source .venv/bin/activate && ruff check src/portallens/wifi tests/test_wifi.py` — All checks passed
  - `source .venv/bin/activate && mypy src/portallens` — Success: no issues found in 40 source files
  - `source .venv/bin/activate && pytest -q` — 245 passed
  - `git diff --check` — passed
  - `git pull --ff-only && git push origin main` — product commit ec62769 pushed successfully using the user's existing credentials
- **Previously verified commands:**
  - `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"` — creates the venv and installs dev deps
  - `.venv/bin/portallens analyze "<url>" "<url>"` — renders the Markdown report on stdout
  - `sh .context/core/bin/context-sync update` — core 0.3.0 → 0.5.0 applied cleanly (session 9); verify + status pass post-update
- **Git identity:** repo-local `user.name`/`user.email` set to `Tisone Kironget <tisonkironget@gmail.com>` (confirmed Session 17 with `git var GIT_AUTHOR_IDENT`).
- **Quirks:**
  - **Reach for `python3.12`, never bare `python3`** — the bare one is 3.9 and will fail on this project's syntax and typing.
  - `.venv/` is gitignored; a fresh clone needs the venv step above before anything runs.
  - `git worktree add <path> <sha>` works and is a clean way to render "before" output for a refactor diff. Remove it with `git worktree remove <path>` when done.

---
## Tisone's Windows workstation (last verified 2026-07-23)
- **Identify by:** repo at `C:\Users\tison\Dev\PortalLens`, Windows 11, local IDE agent (GitHub Copilot), user's own git credentials
- **OS:** Windows 11 (10.0.22631)
- **Runtimes:** `C:\Python314\python.exe` (Python 3.14.2) is installed, but the project uses `.venv\Scripts\python` (3.14.2) inside the repo's venv at `C:\Users\tison\Dev\PortalLens\.venv\`
- **Package manager:** pip inside the project `.venv`
- **Verified commands:**
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
