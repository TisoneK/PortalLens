# Session 15+ Research Questions

**Logged from:** Session 14 (Buffy / 2026-08-02 / plan-only) — three followups
flagged at session close. These are **research markers**: questions to
investigate or design work to do before any producer code lands. They
are not new implementation backlog items in their own right.

For each item: trigger followup, status, pointers to existing work in
this repo, research questions, what the research informs, and a priority
note for whoever picks this up.

---

## R1 — ADR-shape decisions for per-action capabilities (default-cred, L2 MAC impersonation)

**Trigger followup:** "Decide on ADR-19 + draft ADRs 20/21"
**Status:** ADR-19 drafted (status: `proposed`) for session replay.
ADR-20 (default-cred) and ADR-21 (MAC) are **not drafted yet** —
sharp shape TBD per research below.

**Where the existing work lives:**
- `.context/memory/plans/decisions.md` — ADR-19 (read first as the
  proposed exemplar).
- `.context/memory/tasks/backlog.md` — three meta-items already
  appended this session: "Per-action ADR-16 review: default-credential
  authentication", "Per-action ADR-16 review: L2 MAC impersonation",
  "Per-action ADR-16 review: captured-token session replay".
- ADR-15 (single `--authorized` flag is the consent model),
  ADR-16 (per-action risk-assessment discipline), ADR-18 (probe-only
  "never authenticate / submit credentials / send exploit payloads /
  obtain access" boundary) bind the decision space.

**Research questions:**

1. **What is the right shape for the default-cred ADR?**
   - ADR-19's three-category split (synthetic / owned-target /
     captured-real) was clean for session replay because the bearer
     of authorization (token) and the bearer of access (operator)
     are cleanly separable.
   - For default credentials, the analogous split is messier: the
     *target* is the same in each category (an admin interface), but
     the *authenticator* changes. Is "owned creds tested against
     owned target" a meaningful category, or a relic of testing
     convention?
   - Alternative shape: **auth-mechanism bucketed**
     (`HTTP basic` / `HTTP form` / `SSH password` / `SSH key` /
     `SNMP community string` / `RADIUS shared secret`), each with
     its own per-mechanism risk assessment and acceptance criteria.
   - Alternative shape: **binary lab-vs-live**
     (`--lab-only` mode enforcing testbed-only targets + a
     hardcoded credential allowlist).
2. **What is the right shape for L2 MAC impersonation ADR?**
   - Three category likely does not fit (target = who you impersonate
     is the operator's privileged carry-over from the network, not a
     separate auth-bearer dimension).
   - Binary lab-vs-live fits cleanly: `--lab-only` flag + a bSSID
     allowlist + state rollback guarantee + `dry-run` default
     ensures the operator cannot accidentally MAC-spoof a live
     client.
   - Cross-cutting: MAC-station correlation can become org profiling
     (ADR-12 bounded-BI bound). The dry-run default is also the
     org-profiling guard here.
3. **Cross-cutting research:** are there discoverable classification
   conventions in security-testing literature (OWASP / NIST / SANS
   / PTES) for "assess vs exploit vs impersonate vs replay" boundaries?
   Reference text would tighten the ADR prose.

**What this research informs:**
- The wording of the two new meta-items in `tasks/backlog.md`
  (currently says "the ADR must either (a) accept or (b) refuse" —
  this is a coarse split; the real ADR likely wants more nuance
  per auth mechanism for default-cred).
- Whether Session 15 should start with the per-action ADRs (R1
  gating) or the passive `co_host_enumerate` step (R2, no gating).

**Priority:** Highest — explicitly flagged by the user as requiring
their decision; shapes the wording of two backlog meta-items.

---

## R2 — `co_host_enumerate` AnalysisStep (passive, sibling of `resolve_dns` / `ip_asn_lookup`)

**Trigger followup:** "Build co_host_enumerate step"
**Status:** Backlog entry already exists (added Session 14). No code
written yet.

**Where the existing work lives:**
- `.context/memory/tasks/backlog.md` — entry "Reverse DNS /
  co-host enumeration".
- `.context/memory/sessions/2026-08-02-10/notes.md` (Session 10)
  — `resolve_dns` step reference implementation.
- `src/portallens/steps/dns.py` — `resolve_dns` AnalysisStep
  precedent (read first to copy shape).
- `src/portallens/steps/ip_asn.py` — `ip_asn_lookup` AnalysisStep
  precedent (sibling shape).
- `src/portallens/evidence.py` — `EvidenceType` enum (new entry
  `CO_HOST_PAIR` would land here).
- ADR-9 (analysis-step registry) — `slug` / `label` / `requires` /
  `produces` / `answers` declarations.

**Research questions:**

1. **PTR-data freshness:** what TTL window is meaningful for
   "currently co-hosted"? Skip if stale: yes/no, threshold? PTR
   records can have high TTL (sometimes >24h) and stale PTR won't
   reflect current co-hosting.
2. **Multi-IP targets:** should the step coalesce IPs into one
   enumeration pass, or run per-IP? Practical consideration: if
   the report has 5 gateway IPs and each returns 30 PTR names,
   the merged evidence list could be 150 items — re-think.
3. **CT-log overlap:** the existing backlog item "Certificate
   Transparency log mining" surfaces operators sharing cert
   infrastructure (cert side-channel). `co_host_enumerate`
   surfaces operators sharing IP infrastructure (DNS side-channel).
   Are relationship signals *independent* (combine via noisy-OR per
   ADR-2) or *correlated* (one operator may consistently co-host)?
   The relationship inference layer (the `SAME_OPERATOR` /
   `USES_PLATFORM` inference rules in `src/portallens/plugins/
   captive_wifi/relationship.py`) may want both signals as input.
4. **ADR-12 bounded-BI check:** is "list other domains on this IP"
   still passive infrastructure enumeration, or does it cross into
   org profiling? The ADR-3 hypothesis cap on `RESELLS_BANDWIDTH`
   (low) is the standing guarantee against "org profiling feels
   accurate." If `co_host_enumerate` feeds a `SAME_OPERATOR`
   inference, the same ADR-3 cap should apply.

**What this research informs:**
- The exact `AnalysisStep` shape (slug `co_host_enumerate`,
  `requires = resolve_dns`, `produces = [CO_HOST_PAIR]`).
- Evidence-type addition to enum (`CO_HOST_PAIR`) — idempotent
  no-migration schema addition per ADR-14.
- Renderer / TUI hooks for `CO_HOST_PAIR` display.
- Whether `relationship.py` needs a small enhancement (PTR + cert
  → SAME_OPERATOR) or whether the two signals combine cleanly
  through ADR-2 noisy-OR at the relationship-inference layer.

**Priority:** Lower (self-contained, no ADR gating). Candidate
Session-15 starter *if* R1's per-action ADRs aren't the
preferred opening.

---

## R3 — Pre-existing mypy strict baseline (deferred bug-fix)

**Trigger followup:** "Fix pre-existing mypy strict errors"
**Status:** Known issue from Session 13 baseline. Not addressed in
Session 14 (out of scope — plan-only). 17 errors total,
all in `tests/`, none in `src/`.

**Concrete locations** (from `mypy --strict src tests 2>&1 | tail -5`):
- `tests/test_tui.py:228` — `Function is missing a type annotation
  [no-untyped-def]`.
- `tests/test_bypass.py:194/224/238` — `Argument "portal_type" to
  "PortalReport" has incompatible type "str"; expected "PortalType"
  [arg-type]`.
- 17 total errors in 5 files (the remaining 13 not enumerated here
  — full output via `mypy --strict src tests` when needed).

**Where the context lives:**
- `workflows/active.md` — standing expectation: "ruff + mypy strict
  clean". Today pytest (220) passes; mypy strict is the higher bar
  that's currently red.
- `.context/memory/inefficiencies/log.md` (this session) —
  Session-14 entries; this item lands alongside.
- `src/portallens/portal.py` — read for the `PortalReport` model's
  `portal_type` field type (likely `PortalType` enum; the test
  callers passing `str` are either relic convention or a real bug).

**Research questions:**

1. Is the `portal_type: str` annotation in three test locations
   deliberate string-union convenience, or a leftover from an
   earlier API where `PortalType` re-exported `str` (pre-Session-5
   registry work)? If the latter, the fix is one-line per
   occurrence (`portal_type=PortalType.CAPTIVE_WIFI` etc.).
2. The `test_tui.py:228` annotation gap is likely a fixture
   helper written without annotation when Session 4 TUI landed.
   The fix is trivial (add `-> None` or parameter types).
3. Have `tests/` files added since Session 10 been drifted? The
   Session-11 `code-reviewer` flagged cp1252 encoding boundary
   hygiene; type-annotation drift may have a similar pattern
   worth a spot-check across all `tests/*.py`.
4. Is `mypy --strict` actually the right gate, or would `ruff`
   custom rules + a tighter `pyright` baseline serve the same
   purpose without the cost? (Out of scope this session — flag
   for future workflow discussion.)

**What this research informs:**
- Three precise edit locations (or however many the real count
  is) in `tests/`.
- Whether `workflows/active.md` should re-assert mypy strict as
  the gate, or relax toward ruff-only for daily sessions.
- Whether a pre-merge `mypy --strict` hook would have caught this
  drift before the second session hard-coded it.

**Priority:** Lowest. Mechanical fix; any session can do it.

---

## Research queue priority (when Session 15 starts)

If a single research deliverable is the opener:
- **R1** is highest leverage — the user explicitly flagged the
  ADR-shape question and it gates wording in two backlog meta-items.
- **R2** is a clean self-contained implementation piece when
  R1 isn't.
- **R3** is the lowest-effort cleanup; can land in any session.

---

## Conventions used in this notes file

- Each research item carries: trigger, status, repo pointers
  (file paths), questions, "what this informs" section, priority.
- This file lives in the Session-14 notes directory
  (`.context/memory/sessions/2026-08-02-14/`) for continuity with
  `notes.md`. A future agent reading the session notes will
  encounter `research-questions.md` adjacent and know there are
  three research threads to consider.
- The standing convention from `.context/core/schemas/context-schema.md`
  applies: this file is project DATA, written once and read many
  times. Future agents append at the bottom or open new versioned
  files; do **not** delete or rewrite existing entries.
