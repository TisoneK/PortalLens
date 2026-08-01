"""The :class:`Investigation` aggregate — PortalLens's persisted unit of work.

Until now PortalLens was stateless: URLs in, :class:`~portallens.portal.PortalReport`
out. ADR-8 introduces the :class:`Investigation` — a durable record of a target,
the report produced for it, the authorizations the operator has asserted, and an
append-only audit log of everything that happened. It is the shared foundation
the TUI and the future DisclosureDesk both build on.

An investigation carries three things a bare report does not:

- **Identity and time** — a stable id, and created/updated timestamps, so the
  same target can be revisited and its history kept.
- **An authorization record** (ADR-10) — which active techniques the operator
  asserted authorization for, each stamped with the moment it was asserted.
  This is not a boolean badge: you can be authorized to resolve DNS and not to
  port-scan. For a disclosure report, "I asserted authorization for DNS at
  14:31 before running it" is itself evidence, so it lives in the record.
- **An audit log** — an append-only trail of what was done and when. It is what
  makes a finding defensible weeks later.

The report is still the immutable snapshot; the investigation is the mutable,
persisted aggregate that owns it. ``analyze()`` is "step zero" — the passive
bootstrap that seeds the report. Later analysis steps (ADR-9) will append to it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from portallens.evidence import Evidence
from portallens.portal import AcquisitionPolicy, PortalReport, PortalType


def _utcnow() -> datetime:
    """Timezone-aware current UTC time.

    Always UTC, never naive — an audit trail whose timestamps are in an
    unstated local zone is worse than useless when the disclosure is read
    from a different one.
    """

    return datetime.now(timezone.utc)


def _active_techniques() -> frozenset[str]:
    """The set of active-technique names an authorization can name.

    Derived from :class:`AcquisitionPolicy`'s boolean fields rather than
    hardcoded, so when ADR-13 adds ``use_osint_apis`` / ``execute_scripts``
    they become valid authorization targets automatically — no edit here.
    """

    probe = AcquisitionPolicy()
    return frozenset(name for name, value in vars(probe).items() if isinstance(value, bool))


#: Active techniques an :class:`AuthorizationGrant` may name. Kept in sync with
#: :class:`AcquisitionPolicy` automatically (see :func:`_active_techniques`).
ACTIVE_TECHNIQUES: frozenset[str] = _active_techniques()


class AuthorizationGrant(BaseModel):
    """An assertion, by the operator, that they are authorized to run one
    active technique against this investigation's target.

    Per ADR-10 this is per-technique and timestamped. The library cannot
    verify the assertion — it records who claimed what, and when, so the
    claim travels with the finding.
    """

    technique: str
    granted_at: datetime = Field(default_factory=_utcnow)
    note: str | None = None


class AuditEntry(BaseModel):
    """One line in an investigation's append-only audit log."""

    at: datetime = Field(default_factory=_utcnow)
    kind: str
    detail: str


class Investigation(BaseModel):
    """A persisted investigation into one portal target.

    Construct new investigations with :meth:`start` rather than the raw
    constructor — it stamps the timestamps and opens the audit log with a
    ``created`` entry.
    """

    id: str
    target: str
    portal_type: PortalType
    report: PortalReport
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    authorizations: list[AuthorizationGrant] = Field(default_factory=list)
    audit_log: list[AuditEntry] = Field(default_factory=list)
    user_notes: str | None = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def start(
        cls,
        report: PortalReport,
        *,
        portal_type: PortalType,
        user_notes: str | None = None,
    ) -> Investigation:
        """Begin an investigation from a report produced by step zero.

        The id is derived from the target's hostname plus a short random
        suffix — human-recognizable, but unique across revisits of the same
        target.
        """

        now = _utcnow()
        target = report.primary_url
        inv = cls(
            id=_make_id(target),
            target=target,
            portal_type=portal_type,
            report=report,
            created_at=now,
            updated_at=now,
            user_notes=user_notes,
        )
        inv.record("created", f"Investigation opened for {target!r} (passive analysis — step zero).")
        return inv

    # ------------------------------------------------------------------
    # Audit + authorization
    # ------------------------------------------------------------------

    def append_evidence(self, evidence: list[Evidence], *, step: str) -> None:
        """Append analysis-step evidence to the report (ADR-9).

        ``step`` is the slug of the :class:`~portallens.steps.registry.AnalysisStep`
        that produced the evidence — it lands in the audit log so the trail
        records *what* was appended, *when*, and *by which step*. Bumps
        ``updated_at`` like any other mutation.
        """

        if not evidence:
            return
        self.report.evidence.extend(evidence)
        self.record(
            "step",
            f"Analysis step {step!r} appended {len(evidence)} evidence records.",
        )

    def record(self, kind: str, detail: str) -> AuditEntry:
        """Append an entry to the audit log and bump ``updated_at``."""

        entry = AuditEntry(kind=kind, detail=detail)
        self.audit_log.append(entry)
        self.updated_at = entry.at
        return entry

    def authorize(self, technique: str, *, note: str | None = None) -> AuthorizationGrant:
        """Record that the operator asserts authorization for ``technique``.

        Raises :class:`ValueError` if ``technique`` is not a recognized active
        technique. Re-authorizing an already-authorized technique is allowed
        and appends a fresh, separately-timestamped grant — the audit trail
        keeps every assertion rather than collapsing them.
        """

        if technique not in ACTIVE_TECHNIQUES:
            known = ", ".join(sorted(ACTIVE_TECHNIQUES))
            raise ValueError(f"unknown active technique {technique!r}; known techniques: {known}")
        grant = AuthorizationGrant(technique=technique, note=note)
        self.authorizations.append(grant)
        self.record("authorized", f"Authorization asserted for {technique!r}" + (f": {note}" if note else "."))
        return grant

    def is_authorized(self, technique: str) -> bool:
        """True iff at least one authorization grant names ``technique``."""

        return any(g.technique == technique for g in self.authorizations)

    @property
    def authorized_techniques(self) -> set[str]:
        """The distinct set of techniques the operator has authorized."""

        return {g.technique for g in self.authorizations}


def _make_id(target: str) -> str:
    """A stable, human-recognizable investigation id from a target.

    ``https://captive.ispman.tech/...`` → ``captive-ispman-tech-1a2b3c``. The
    slug is derived from the actual target the user supplied (that is data, not
    a hardcoded example); the suffix keeps revisits distinct.
    """

    from urllib.parse import urlparse

    host = (urlparse(target).hostname or target).lower()
    slug = "".join(c if c.isalnum() else "-" for c in host).strip("-") or "portal"
    # Collapse runs of dashes so a messy target doesn't produce "a---b".
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"{slug}-{uuid.uuid4().hex[:6]}"
