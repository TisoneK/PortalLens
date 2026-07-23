"""Relationship inference for captive Wi-Fi portals.

Given evidence captured from one or more captive-portal URLs, this module
infers relationships between the hosts involved (e.g. the redirect target in
``link-login``). Every relationship carries a confidence score and the
evidence ids it rests on.

The key insight — lifted directly from the PortalLens design — is that
a single observed redirect (e.g. ``maz.wifi`` → ``captive.ispman.tech``)
supports some inferences very strongly ("the portal uses ISPMan") but
NOT others ("ISPMan operates the Wi-Fi network", "Maz resells upstream
bandwidth"). The detector below encodes that asymmetry explicitly.

Which hosts are platform providers is not decided here: it comes from
:func:`portallens.plugins.captive_wifi.signatures.platform_for_host`. This
module names no vendor, so a provider added to the registry gets the same
``USES_PLATFORM`` / ``AUTHENTICATES_FOR`` / ``RESELLS_BANDWIDTH`` reasoning
ISPMan gets, with no change here.

Redirect direction
------------------
MikroTik's ``link-login`` parameter on an external portal URL points
BACK at the hotspot's login page (e.g. ISPMan's URL has
``link-login=http://maz.wifi/login?...``). That means the URL carrying
the ``link-login`` parameter is the redirect TARGET, and the host the
parameter points at is the redirect SOURCE.

So if URL A (host = captive.ispman.tech) has ``link-login=http://maz.wifi/...``,
the redirect direction is: ``maz.wifi`` → ``captive.ispman.tech``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from portallens.confidence import score
from portallens.evidence import Evidence, EvidenceType
from portallens.plugins.captive_wifi.signatures import (
    BACKLINK_PARAMS,
    PortalSignature,
    platform_for_host,
)
from portallens.portal import PortalRelationship, RelationshipKind

if TYPE_CHECKING:
    from portallens.plugins.captive_wifi.url_parser import CaptivePortalURLHints

#: Below this, the evidence is too thin to publish even as a hypothesis.
MIN_RELATIONSHIP_CONFIDENCE = 20

#: Evidence key the analyzer uses for redirects extracted from `link-login`.
BACKLINK_EVIDENCE_KEY = "link_login_target"

#: Hostname suffixes that only resolve inside a local network. A captive
#: portal served from one of these is the operator's own gateway, never a
#: hosted platform.
_LOCAL_TLDS = (".wifi", ".local", ".lan", ".internal")


@dataclass
class RelationshipInference:
    """A single inferred relationship, before being finalized into a
    :class:`PortalRelationship` for the report."""

    kind: RelationshipKind
    other: str
    confidence: int
    evidence_ids: list[str] = field(default_factory=list)
    note: str | None = None


def infer_relationships(
    hints: CaptivePortalURLHints,
    evidence: list[Evidence],
    all_urls: list[str],
) -> list[PortalRelationship]:
    """Infer relationships between portal hosts and other entities.

    ``all_urls`` is the full list of URLs the user supplied. The
    analyzer scans every URL's evidence (not just the primary URL's)
    for redirect signals — a ``link-login`` parameter on URL A pointing
    at host B implies a redirect from B to A.

    The function returns relationships sorted by confidence, highest
    first. Relationships below :data:`MIN_RELATIONSHIP_CONFIDENCE` are
    dropped.
    """

    inferences: list[RelationshipInference] = []

    primary_host = hints.parsed.host.lower()
    redirect_pairs = _redirect_pairs(evidence)

    # ------------------------------------------------------------------
    # 1. REDIRECTS_TO — high confidence for observed redirect evidence.
    # ------------------------------------------------------------------
    for (source, target), ev_ids in redirect_pairs.items():
        # Base weight per evidence record. Multiple link-* parameters
        # pointing the same direction reinforce each other.
        confidence = score([50] * len(ev_ids))
        if confidence.value >= MIN_RELATIONSHIP_CONFIDENCE:
            inferences.append(
                RelationshipInference(
                    kind=RelationshipKind.REDIRECTS_TO,
                    other=f"{source} → {target}",
                    confidence=confidence.value,
                    evidence_ids=ev_ids,
                    note=f"`{source}` redirects to `{target}` (observed via gateway back-link parameter on the target URL).",
                )
            )

    # ------------------------------------------------------------------
    # 2. USES_PLATFORM + AUTHENTICATES_FOR — a redirect landing on a
    #    registered hosted platform means the source operator uses that
    #    platform as its portal backend.
    # ------------------------------------------------------------------
    for source, platform, ev_ids in _platform_redirects(redirect_pairs, hints, primary_host):
        # Redirect observed + platform host fingerprint.
        uses_confidence = score([60, 50])
        inferences.append(
            RelationshipInference(
                kind=RelationshipKind.USES_PLATFORM,
                other=f"{source} → {platform.platform}",
                confidence=uses_confidence.value,
                evidence_ids=ev_ids,
                note=(
                    f"`{source}` operates a captive portal that uses "
                    f"{platform.platform} as its platform/backend."
                ),
            )
        )
        auth_confidence = score([75])
        inferences.append(
            RelationshipInference(
                kind=RelationshipKind.AUTHENTICATES_FOR,
                other=f"{platform.platform} → {source}",
                confidence=auth_confidence.value,
                evidence_ids=ev_ids,
                note=(
                    f"{platform.platform} captive portal handles authentication "
                    f"for `{source}`'s hotspot."
                ),
            )
        )

    # ------------------------------------------------------------------
    # 3. OPERATES_NETWORK — local-only hostnames that serve captive
    #    portals are likely the network operator. A host owned by a
    #    registered platform provider never qualifies.
    # ------------------------------------------------------------------
    for host in sorted(_observed_hosts(evidence, all_urls)):
        if platform_for_host(host) is not None:
            continue
        if not _is_local_hostname(host):
            continue
        ev_ids = [
            ev.id for ev in evidence
            if ev.type is EvidenceType.URL_HOST and ev.value.lower() == host
        ]
        confidence = score([65, 25])  # local hostname + serves captive portal
        inferences.append(
            RelationshipInference(
                kind=RelationshipKind.OPERATES_NETWORK,
                other=host,
                confidence=confidence.value,
                evidence_ids=ev_ids,
                note=(
                    f"`{host}` serves a captive portal on a local-only "
                    "TLD — the entity behind this hostname most likely operates "
                    "the underlying Wi-Fi network. The upstream bandwidth "
                    "provider is NOT identified by this evidence."
                ),
            )
        )

    # ------------------------------------------------------------------
    # 4. RESELLS_BANDWIDTH — explicitly low confidence. The redirect
    #    cannot distinguish a reseller from an operator that merely buys
    #    a portal product. Capped at 35 per ADR-3.
    # ------------------------------------------------------------------
    for (source, target), _ in sorted(redirect_pairs.items()):
        target_platform = platform_for_host(target)
        if target_platform is None:
            continue
        ev_ids = _platform_evidence_ids(evidence, target_platform)
        confidence = score([35])
        inferences.append(
            RelationshipInference(
                kind=RelationshipKind.RESELLS_BANDWIDTH,
                other=f"{source} resells upstream bandwidth",
                confidence=confidence.value,
                evidence_ids=ev_ids,
                note=(
                    "Speculative: the captive-portal redirect alone cannot "
                    "distinguish a reseller from an operator using a 3rd-party "
                    "platform. Resolving this requires package-pricing evidence, "
                    "upstream ISP identification (ASN/IP ownership), or direct "
                    "operator disclosure."
                ),
            )
        )

    # ------------------------------------------------------------------
    # 5. Finalize.
    # ------------------------------------------------------------------
    out = [
        PortalRelationship(
            kind=inf.kind,
            other=inf.other,
            confidence=inf.confidence,
            evidence_ids=inf.evidence_ids,
            note=inf.note,
        )
        for inf in inferences
        if inf.confidence >= MIN_RELATIONSHIP_CONFIDENCE
    ]
    out.sort(key=lambda r: -r.confidence)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_backlink(ev: Evidence) -> bool:
    """True for evidence that points back at the host we were redirected from."""

    if ev.type is EvidenceType.URL_PARAMETER:
        return ev.key in BACKLINK_PARAMS
    if ev.type is EvidenceType.URL_REDIRECT:
        return ev.key == BACKLINK_EVIDENCE_KEY
    return False


def _redirect_pairs(evidence: list[Evidence]) -> dict[tuple[str, str], list[str]]:
    """Build the redirect graph from gateway back-link evidence.

    Returns ``{(source_host, target_host): [evidence_id, ...]}``. See this
    module's docstring for why the parameter's host is the *source* and the
    URL carrying it is the *target*.
    """

    pairs: dict[tuple[str, str], list[str]] = {}
    for ev in evidence:
        if not _is_backlink(ev):
            continue
        source_host = (urlparse(ev.value).hostname or "").lower()
        target_host = (urlparse(ev.source).hostname or "").lower()
        if not source_host or not target_host or source_host == target_host:
            continue
        pairs.setdefault((source_host, target_host), []).append(ev.id)
    return pairs


def _platform_redirects(
    redirect_pairs: dict[tuple[str, str], list[str]],
    hints: CaptivePortalURLHints,
    primary_host: str,
) -> list[tuple[str, PortalSignature, list[str]]]:
    """Redirects whose target is a registered hosted platform.

    Also covers the case where the analyzed URL *is* the platform's: then the
    redirect we hold points at the primary host, and the operator is on the
    other end of it.
    """

    out: list[tuple[str, PortalSignature, list[str]]] = []
    seen: set[tuple[str, str]] = set()

    for (source, target), ev_ids in sorted(redirect_pairs.items()):
        platform = platform_for_host(target)
        if platform is None:
            continue
        if (source, platform.slug) in seen:
            continue
        seen.add((source, platform.slug))
        out.append((source, platform, ev_ids))

    own_platform = hints.platform
    if own_platform is not None:
        for (source, target), ev_ids in sorted(redirect_pairs.items()):
            if target != primary_host or own_platform.owns_host(source):
                continue
            if (source, own_platform.slug) in seen:
                continue
            seen.add((source, own_platform.slug))
            out.append((source, own_platform, ev_ids))

    return out


def _observed_hosts(evidence: list[Evidence], all_urls: list[str]) -> set[str]:
    """Every hostname seen in the supplied URLs or captured as evidence."""

    hosts = {(urlparse(url).hostname or "").lower() for url in all_urls}
    hosts |= {ev.value.lower() for ev in evidence if ev.type is EvidenceType.URL_HOST}
    hosts.discard("")
    return hosts


def _is_local_hostname(host: str) -> bool:
    """True for hostnames that only resolve inside a local network."""

    return host.endswith(_LOCAL_TLDS) or "." not in host


def _platform_evidence_ids(evidence: list[Evidence], platform: PortalSignature) -> list[str]:
    """Evidence records that place the redirect on ``platform``'s host."""

    out: list[str] = []
    for ev in evidence:
        source_host = (urlparse(ev.source).hostname or "").lower()
        if platform.owns_host(source_host) and _is_backlink(ev):
            out.append(ev.id)
    return out
