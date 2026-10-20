# Active Workflow (overwrite when the workflow changes)

The workflow currently in force for this repo — which protocol edition
agents follow and the standing session parameters. Update only when the
user changes the rules; note the change in your session entry.

- **Protocol:** by agent type — local agents → `.context_ledger/core/rules/ai-engineering-protocol-local.md`; cloud/sandbox agents → `.context_ledger/core/rules/ai-engineering-protocol.md`
  <!-- ALWAYS record it exactly like that — "by agent type", naming BOTH.
  NEVER record only the edition YOU happen to be: the next agent on this
  project may be the other type, will read this field as binding, and
  will inherit your platform's behavior (a local agent doing cloud PAT
  dances, or a cloud agent skipping its clone). The edition is a
  per-agent-type fact, not a project fact. -->
- **Protocol location:** on disk — vendored in `.context_ledger/core/` (no network fetch needed; version in `.context_ledger/core/VERSION`, last verified in `../core.lock`)
- **Package upstream (for flaw back-ports + core updates):** https://github.com/TisoneK/.context.git
- **Since:** 2026-07-23 (paths updated by the core 2.2.0 Context Ledger migration, 2026-10-20)
- **Default role:** engineer — full-scope per the edition; role overlays in `.context_ledger/core/roles/` (reviewer, security-auditor, docs-agent, feature-engineer) when a session needs a narrower scope
- **Scope:** discovery + review + feature implementation (MVP scaffold is the standing target until the project has a runnable baseline)
- **Target:** feature — bootstrap PortalLens MVP: plugin-based Portal core abstraction + captive_wifi analyzer (passive: fingerprinting, platform identification, network-architecture inference, relationship mapping) + evidence-backed reporting with confidence scores
- **Focus areas:** architecture, security, testing, docs — security work lives in a separate audit module; active techniques unlock behind a single authorization (ADR-15); the assess/exploit boundary is lifted (ADR-16) with no exploit capability built yet; findings may be lightweight (ADR-17). `src/` is aligned with ADR-15/16/17 as of Session 12
- **Findings handling:** fix safe issues; flag architectural changes for explicit approval
- **Push policy:** push to main directly after each commit
- **Commit style:** Conventional Commits with scope (`feat(core):`, `feat(captive_wifi):`, `fix(reporting):`, `docs:`, `chore(ledger):` for `.context_ledger/` updates, `docs(review):` for review reports)
- **Commit granularity:** one logical change per commit
- **Deliverable:** markdown report in `.context_ledger/memory/office/reviews/YYYY-MM-DD-review.md` + chat summary; code in `src/` per the `Portal` plugin architecture
- **Gates:** `.context_ledger/memory/workflows/gates.conf` — checkpoint before each next action; `pre-commit`, `integration`, and `exit` gates are mandatory
