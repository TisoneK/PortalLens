"""Analysis steps (ADR-9) — the "pull the thread" loop.

Importing this package registers every step: ``resolve_dns`` and
``ip_asn_lookup``. The registry lives in :mod:`portallens.steps.registry`;
each step module registers itself on import.
"""

from __future__ import annotations

from portallens.steps import dns as _dns  # noqa: F401 — registers resolve_dns
from portallens.steps import ip_asn as _ip_asn  # noqa: F401 — registers ip_asn_lookup
from portallens.steps.registry import (
    AnalysisStep,
    compute_next_steps,
    hosts_from_report,
    refine_open_questions,
    register_step,
    registered_steps,
    step_for_slug,
)

__all__ = [
    "AnalysisStep",
    "compute_next_steps",
    "hosts_from_report",
    "refine_open_questions",
    "register_step",
    "registered_steps",
    "step_for_slug",
]
