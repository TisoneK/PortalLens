"""Platform fingerprints for captive Wi-Fi portals.

Each fingerprint is a rule that maps a set of evidence observations to a
detected platform with a confidence score. The detector runs every
fingerprint independently — a single URL can match multiple
fingerprints (e.g. a MikroTik hotspot fronted by ISPMan matches both).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from portallens.confidence import score
from portallens.evidence import Evidence, EvidenceType

if TYPE_CHECKING:
    from portallens.plugins.captive_wifi.url_parser import CaptivePortalURLHints


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


def detect_fingerprints(
    hints: CaptivePortalURLHints,
    evidence: list[Evidence],
) -> list[FingerprintMatch]:
    """Run every fingerprint against ``hints`` + ``evidence``.

    Returns all matches with confidence ≥ 20 (below that the evidence
    is too thin to call it a fingerprint — it's a hint, not a
    detection). Sorted by confidence, highest first.
    """

    matches: list[FingerprintMatch] = []
    matches.extend(_detect_mikrotik(hints, evidence))
    matches.extend(_detect_ispman(hints, evidence))
    matches.extend(_detect_coorvachilli(hints, evidence))

    matches = [m for m in matches if m.confidence >= 20]
    matches.sort(key=lambda m: -m.confidence)
    return matches


# ---------------------------------------------------------------------------
# Individual fingerprint detectors
# ---------------------------------------------------------------------------

def _detect_mikrotik(
    hints: CaptivePortalURLHints,
    evidence: list[Evidence],
) -> list[FingerprintMatch]:
    from portallens.plugins.captive_wifi.url_parser import CaptivePortalFlavor

    if CaptivePortalFlavor.MIKROTIK not in hints.flavors:
        return []

    # The canonical MikroTik signature is the presence of link-login +
    # link-orig + dst in the query string. Each contributes weight:
    #   - link-login present: 50 (very specific to MikroTik)
    #   - link-orig present:  40
    #   - dst present:        20 (also used by Apple captive probe)
    #   - mac + ip present:   20 (also emitted by CoovaChilli, but the
    #                              combination is mostly MikroTik in the
    #                              field)
    weights: list[int] = []
    ev_ids: list[str] = []
    for ev in evidence:
        if ev.type is EvidenceType.URL_PARAMETER and ev.source == hints.parsed.raw:
            if ev.key == "link-login":
                weights.append(55)
                ev_ids.append(ev.id)
            elif ev.key == "link-orig":
                weights.append(40)
                ev_ids.append(ev.id)
            elif ev.key == "link-login-only":
                weights.append(45)
                ev_ids.append(ev.id)
            elif ev.key == "dst":
                weights.append(20)
                ev_ids.append(ev.id)
            elif ev.key in {"mac", "ip"}:
                weights.append(10)
                ev_ids.append(ev.id)
    confidence = score(weights)
    if confidence.value < 20:
        return []
    return [
        FingerprintMatch(
            platform="MikroTik RouterOS Hotspot",
            confidence=confidence.value,
            evidence_ids=ev_ids,
            note="Query-string signature matches MikroTik RouterOS hotspot login variables.",
        )
    ]


def _detect_ispman(
    hints: CaptivePortalURLHints,
    evidence: list[Evidence],
) -> list[FingerprintMatch]:
    from portallens.plugins.captive_wifi.url_parser import CaptivePortalFlavor

    if CaptivePortalFlavor.ISPMAN not in hints.flavors:
        return []

    # ISPMan's URL pattern is very specific — host suffix + path scheme
    # together carry high weight. We don't need query params.
    weights: list[int] = []
    ev_ids: list[str] = []
    for ev in evidence:
        if ev.type is EvidenceType.URL_HOST and ev.source == hints.parsed.raw:
            weights.append(60)
            ev_ids.append(ev.id)
        if ev.type is EvidenceType.URL_PATH and ev.source == hints.parsed.raw:
            weights.append(50)
            ev_ids.append(ev.id)
    confidence = score(weights)
    if confidence.value < 20:
        return []
    return [
        FingerprintMatch(
            platform="ISPMan",
            confidence=confidence.value,
            evidence_ids=ev_ids,
            note="URL host + path match ISPMan captive-portal scheme (captive.ispman.tech/hotspots/.../select).",
        )
    ]


def _detect_coorvachilli(
    hints: CaptivePortalURLHints,
    evidence: list[Evidence],
) -> list[FingerprintMatch]:
    from portallens.plugins.captive_wifi.url_parser import CaptivePortalFlavor

    if CaptivePortalFlavor.COOVACHILLI not in hints.flavors:
        return []

    weights: list[int] = []
    ev_ids: list[str] = []
    for ev in evidence:
        if ev.type is EvidenceType.URL_PARAMETER and ev.source == hints.parsed.raw:
            if ev.key == "challenge":
                weights.append(55)
                ev_ids.append(ev.id)
            elif ev.key == "userurl":
                weights.append(30)
                ev_ids.append(ev.id)
            elif ev.key in {"uamip", "uamport", "nasid"}:
                weights.append(35)
                ev_ids.append(ev.id)
    confidence = score(weights)
    if confidence.value < 20:
        return []
    return [
        FingerprintMatch(
            platform="CoovaChilli",
            confidence=confidence.value,
            evidence_ids=ev_ids,
            note="Query-string signature matches CoovaChilli captive-portal variables.",
        )
    ]
