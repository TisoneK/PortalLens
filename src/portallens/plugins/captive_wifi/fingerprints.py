"""Platform fingerprints for captive Wi-Fi portals.

A fingerprint maps evidence to a detected platform with a confidence score.
The rules themselves live in
:mod:`portallens.plugins.captive_wifi.signatures` — this module is the
engine that runs them, and knows no vendor by name.

Every signature that fired during URL parsing is scored independently, so a
single URL can produce several fingerprints (the ISPMan fixture yields both
``ISPMan`` and ``MikroTik RouterOS Hotspot`` — a hosted platform fronting an
on-premise gateway).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from portallens.confidence import score
from portallens.evidence import Evidence, EvidenceType
from portallens.plugins.captive_wifi.signatures import SIGNATURES, PortalSignature, Provenance

if TYPE_CHECKING:
    from portallens.plugins.captive_wifi.url_parser import CaptivePortalURLHints

#: A fingerprint below this confidence is a hint, not a detection.
MIN_FINGERPRINT_CONFIDENCE = 20


@dataclass
class FingerprintMatch:
    """A single fingerprint's verdict on a set of evidence.

    ``platform`` is the canonical name (``"MikroTik RouterOS"``,
    ``"ISPMan"``, …). ``confidence`` is in ``[0, 100]``. ``evidence_ids``
    is the list of evidence records the match rests on — the report
    renderer surfaces these so a reader can verify the call.
    """

    platform: str
    confidence: int
    evidence_ids: list[str] = field(default_factory=list)
    version: str | None = None
    note: str | None = None
    #: Slug of the signature that produced the match.
    slug: str | None = None


def detect_fingerprints(
    hints: CaptivePortalURLHints,
    evidence: list[Evidence],
) -> list[FingerprintMatch]:
    """Run every signature that fired on ``hints`` against ``evidence``.

    Returns all matches with confidence ≥ :data:`MIN_FINGERPRINT_CONFIDENCE`
    (below that the evidence is too thin to call it a fingerprint — it's a
    hint, not a detection). Sorted by confidence, highest first.
    """

    matches: list[FingerprintMatch] = []
    for signature in SIGNATURES:
        if signature.slug not in hints.flavors:
            continue
        match = _score_signature(signature, hints, evidence)
        if match is not None:
            matches.append(match)

    matches.sort(key=lambda m: -m.confidence)
    return matches


def _score_signature(
    signature: PortalSignature,
    hints: CaptivePortalURLHints,
    evidence: list[Evidence],
) -> FingerprintMatch | None:
    """Combine every piece of evidence this signature weights into one score.

    Weights come from the signature record and are combined by the noisy-OR
    rule in :func:`portallens.confidence.score` (ADR-2), so independent
    signals reinforce each other without any one of them dominating.
    """

    source = hints.parsed.raw
    weights: list[int] = []
    ev_ids: list[str] = []

    for ev in evidence:
        if ev.source != source:
            continue
        weight = _weight_for(signature, ev)
        if weight is None:
            continue
        weights.append(weight)
        ev_ids.append(ev.id)

    confidence = score(weights)
    if confidence.value < MIN_FINGERPRINT_CONFIDENCE:
        return None

    note = signature.note
    if signature.provenance is not Provenance.VALIDATED:
        note = f"{note} Signature provenance: {signature.provenance.value}."

    return FingerprintMatch(
        platform=signature.platform,
        confidence=confidence.value,
        evidence_ids=ev_ids,
        note=note,
        slug=signature.slug,
    )


def _weight_for(signature: PortalSignature, ev: Evidence) -> int | None:
    """How much this evidence record contributes to ``signature``, if at all."""

    if ev.type is EvidenceType.URL_PARAMETER:
        return signature.param_weights.get(ev.key)
    if ev.type is EvidenceType.URL_HOST and signature.host_weight:
        return signature.host_weight if signature.owns_host(ev.value) else None
    if ev.type is EvidenceType.URL_PATH and signature.path_weight:
        return signature.path_weight
    return None
