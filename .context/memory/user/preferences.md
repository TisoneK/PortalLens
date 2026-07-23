# User Preferences (update in place)

How the user likes things done **on this project**. Seeded from
Pre-Flight at bootstrap; grows as sessions reveal preferences —
corrections the user gives, patterns they approve, things they state
outright. This file exists so the user never has to give the same
correction twice.

## Learning rules

1. **Record preferences, not instructions.** A preference is standing:
   it would apply to future sessions ("plain-language changelog
   entries"). An instruction is one-off ("skip the tests this once") —
   it dies with the session and does not belong here.
2. **Every bullet carries provenance** — how and when it was learned:
   `(pre-flight)`, `(stated, YYYY-MM-DD)`, `(correction, YYYY-MM-DD)`,
   `(approved pattern, YYYY-MM-DD)`. An explicit statement or correction
   outranks an inferred pattern.
3. **Current-state file.** When the user changes their mind, update the
   bullet in place and refresh its provenance — don't keep the stale
   version. History lives in the session log, not here.
4. **A session instruction beats a recorded preference for that
   session.** Follow the instruction; afterwards, if it looked like a
   standing change of mind, update this file.
5. **Committed to git — keep it professional.** Working-style facts
   only. Never personal details, never opinions about people, never
   credentials.

## Workflow

- Push to main directly after each commit (pre-flight, 2026-07-23)
- One logical change per commit (pre-flight, 2026-07-23)
- The `.context/` knowledge system is part of this project from day one — fingerprint/signature databases and analysis methodology should accumulate in `.context/memory/` rather than being rediscovered per session (stated, 2026-07-23)

## Communication

- Plain-language commit messages; technical detail lives in the review report (stated, 2026-07-23)
- When proposing system architecture, present multiple labelled scenarios (A/B/C…) and assign confidence percentages to inferences vs. observed facts — the user prefers calibrated, evidence-backed claims over single confident answers (approved pattern, 2026-07-23)

## Code style

- Plugin-based architecture: name the core abstraction broadly (`Portal`) so future portal types (web auth, payment, ISP) slot in without an architectural rewrite. The first concrete plugin is `captive_wifi` (stated, 2026-07-23)
- Separate the product surface from the security-audit surface — passive analysis (no probing) is the default; active assessment requires explicit authorization (stated, 2026-07-23)
- Vendor/provider knowledge is data, not code. The analyzer must not be centered on whichever provider it was first written against — platform recognition lives in a registry that any provider slots into (correction, 2026-07-23 — the session-2 target was exactly this observation about the MVP)

## Review depth

- Fix safe issues; flag architectural changes for explicit approval before implementing (pre-flight, 2026-07-23)

## Risk & approvals

- Never actively scan or probe networks without authorization — passive analysis only by default (stated, 2026-07-23)
- Vulnerability disclosure must be evidence-backed: a finding states Title, Affected asset, Evidence, Impact, Confidence, Recommended remediation, and Verification status — never bare "your system is insecure" claims (stated, 2026-07-23)
