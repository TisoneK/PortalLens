# Active Workflow (overwrite when the workflow changes)

The workflow currently in force for this repo — which protocol edition
agents follow and the standing session parameters. Update only when the
user changes the rules; note the change in your session entry.

- **Protocol:** by agent type — local agents → `.context/core/rules/ai-engineering-protocol-local.md`; cloud/sandbox agents → `.context/core/rules/ai-engineering-protocol.md`
  <!-- ALWAYS record it exactly like that — "by agent type", naming BOTH.
  NEVER record only the edition YOU happen to be: the next agent on this
  project may be the other type, will read this field as binding, and
  will inherit your platform's behavior (a local agent doing cloud PAT
  dances, or a cloud agent skipping its clone). The edition is a
  per-agent-type fact, not a project fact. -->
- **Protocol location:** on disk — vendored in `.context/core/` (no network fetch needed; version in `.context/core/VERSION`, last verified in `../core.lock`)
- **Package upstream (for flaw back-ports + core updates):** https://github.com/TisoneK/.context.git
- **Since:** 2026-07-23
- **Default role:** engineer — full-scope per the edition; role overlays in `.context/core/roles/` (reviewer, security-auditor, docs-agent, feature-engineer) when a session needs a narrower scope
- **Scope:** discovery + review + feature implementation (MVP scaffold is the standing target until the project has a runnable baseline)
- **Target:** feature — bootstrap PortalLens MVP: plugin-based Portal core abstraction + captive_wifi analyzer (passive: fingerprinting, platform identification, network-architecture inference, relationship mapping) + evidence-backed reporting with confidence scores
- **Focus areas:** architecture, security (passive by default), testing, docs — security-audit/active-scan work is gated behind explicit authorization and lives in a separate audit module, not the passive analyzer
- **Findings handling:** fix safe issues; flag architectural changes for explicit approval
- **Push policy:** push to main directly after each commit
- **Commit style:** Conventional Commits with scope (`feat(core):`, `feat(captive_wifi):`, `fix(reporting):`, `docs:`, `chore(context):` for `.context/` updates, `docs(review):` for review reports)
- **Commit granularity:** one logical change per commit
- **Deliverable:** markdown report in `.context/memory/reviews/YYYY-MM-DD-review.md` + chat summary; code in `src/` per the `Portal` plugin architecture
