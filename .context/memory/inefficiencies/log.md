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
