"""PortalLens — Intelligence and security analysis for digital portals.

The library is built around a single abstract concept, the :class:`Portal`,
with concrete implementations provided by plugins (e.g. ``captive_wifi``).
Every portal produces a :class:`PortalReport` after analysis — an
evidence-backed document that distinguishes observed facts, inferences,
and hypotheses, each carrying an explicit confidence score.

Active probing (HTTP fetching, port scanning, etc.) is gated behind an
explicit :class:`AcquisitionPolicy`. The default policy is **passive** —
analysis works purely from URLs and any user-supplied HTML/HAR payloads.
"""

from __future__ import annotations

from portallens.confidence import Confidence, ConfidenceLabel, score
from portallens.evidence import Evidence, EvidenceType, Observation
from portallens.portal import (
    AnalysisContext,
    Portal,
    PortalFingerprint,
    PortalRelationship,
    PortalReport,
    PortalType,
    RelationshipKind,
)
from portallens.registry import get_portal_class, register_portal

__version__ = "0.1.0"

__all__ = [
    "AnalysisContext",
    "Confidence",
    "ConfidenceLabel",
    "Evidence",
    "EvidenceType",
    "Observation",
    "Portal",
    "PortalFingerprint",
    "PortalRelationship",
    "PortalReport",
    "PortalType",
    "RelationshipKind",
    "__version__",
    "get_portal_class",
    "register_portal",
    "score",
]
