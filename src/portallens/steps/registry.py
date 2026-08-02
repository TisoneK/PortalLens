"""AnalysisStep registry (ADR-9) — analysis steps as data.

A step is a registered, runnable unit of investigation. Each step declares:

- ``slug`` — the stable identifier (open questions name these in their
  ``resolves_with`` lists).
- ``requires`` — the ``AcquisitionPolicy`` technique it needs (``None`` =
  passive). ADR-15 collapsed the per-technique consent model into a single
  ``AcquisitionPolicy.authorized`` flag, so ``requires`` is now **descriptive**
  metadata (which technique the step exercises) rather than a gate the step
  checks against recorded authorizations. The single flag is checked by
  ``assert_policy`` inside the step's ``run``.
- ``produces`` — the evidence types the step emits.
- ``answers`` — the open-question relationship kinds it can answer.
- ``run`` — the executable that turns an investigation into evidence.

The "next investigation" list is **computed**, never hand-maintained
(ADR-9): match open questions' ``resolves_with`` slugs against registered
steps. Register an ASN step and every report that ever asked "who's
upstream?" gains that action automatically.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from portallens.evidence import Evidence, EvidenceType
from portallens.portal import AcquisitionPolicy, OpenQuestion, PortalReport, RelationshipKind

if TYPE_CHECKING:
    from portallens.investigation.models import Investigation


@dataclass(frozen=True)
class AnalysisStep:
    """One registered analysis step."""

    slug: str
    label: str
    requires: str | None  # descriptive: the AcquisitionPolicy technique the step exercises (ADR-15: no longer a per-technique gate)
    produces: tuple[EvidenceType, ...]
    answers: tuple[RelationshipKind, ...]
    run: Callable[[Investigation, AcquisitionPolicy], list[Evidence]]


_STEPS: dict[str, AnalysisStep] = {}


def register_step(step: AnalysisStep) -> None:
    """Register a step. Importing a step's module is what registers it."""

    if step.slug in _STEPS:
        raise ValueError(f"analysis step {step.slug!r} already registered")
    _STEPS[step.slug] = step


def step_for_slug(slug: str) -> AnalysisStep | None:
    """Look a step up by slug, or ``None`` if unregistered."""

    return _STEPS.get(slug)


def registered_steps() -> tuple[AnalysisStep, ...]:
    """Every registered step, in registration order."""

    return tuple(_STEPS.values())


def compute_next_steps(open_questions: list[OpenQuestion]) -> list[AnalysisStep]:
    """The computed "next investigation" queue for ``open_questions``.

    Every step named by an open question's ``resolves_with`` that is actually
    registered appears, in question order, deduplicated. This is ADR-9's
    computed list — the analysis steps a report says would answer its open
    questions, made runnable.
    """

    out: list[AnalysisStep] = []
    seen: set[str] = set()
    for q in open_questions:
        for slug in q.resolves_with:
            step = step_for_slug(slug)
            if step is not None and step.slug not in seen:
                seen.add(step.slug)
                out.append(step)
    return out


def refine_open_questions(
    open_questions: list[OpenQuestion], evidence: list[Evidence]
) -> list[OpenQuestion]:
    """Drop questions the evidence now answers (ADR-9 loop closure).

    The dual of :func:`compute_next_steps`: a question closes once the
    evidence that would answer it exists, so a persisted investigation stops
    re-recommending the steps that already ran. Closure is evidence-driven,
    never hand-maintained:

    - a question whose ``kind`` a registered step ``answers`` closes when that
      step has produced all of its declared evidence types (e.g. the
      upstream-ISP question closes once ``ip_asn_lookup`` produced ``IP_ASN``
      evidence);
    - a question naming the ``port_scan`` step closes when probe evidence
      exists (``SERVICE_REACHABLE``) — the admin-exposure question the
      NetAudit pass answers;
    - questions with no registered answer (empty ``resolves_with``, e.g. a
      DOCUMENTED-signature question) never close — nothing can answer them.
    """

    types = {ev.type for ev in evidence}
    probe_answered = any(ev.type is EvidenceType.SERVICE_REACHABLE for ev in evidence)
    out: list[OpenQuestion] = []
    for q in open_questions:
        # Kind-driven: a registered step that answers this question kind has
        # produced all its evidence types.
        if q.kind is not None:
            if any(
                q.kind in step.answers and all(t in types for t in step.produces)
                for step in registered_steps()
            ):
                continue
        # Probe-driven: the admin-exposure question is answered by NetAudit's
        # SERVICE_REACHABLE evidence, not by a step's evidence types.
        elif "port_scan" in q.resolves_with and probe_answered:
            continue
        out.append(q)
    return out


def hosts_from_report(report: PortalReport) -> list[str]:
    """Unique hostnames observed in a report's evidence and primary URL.

    Step runners use this to decide what to run against.
    """

    from urllib.parse import urlparse

    hosts: list[str] = []
    seen: set[str] = set()

    def add(host: str | None) -> None:
        if not host:
            return
        host = host.lower()
        if host not in seen:
            seen.add(host)
            hosts.append(host)

    add(urlparse(report.primary_url).hostname)
    for ev in report.evidence:
        if ev.type is EvidenceType.URL_HOST:
            add(ev.value)
    return hosts
