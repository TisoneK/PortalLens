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
