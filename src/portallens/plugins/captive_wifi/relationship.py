"""Relationship inference for captive Wi-Fi portals.

Given a :class:`PortalReport` populated with evidence and fingerprints,
this module infers relationships between the portal's host and other
entities observed in the evidence (e.g. the redirect target in
``link-login``). Every relationship carries a confidence score and the
evidence ids it rests on.

The key insight — lifted directly from the PortalLens design — is that
a single observed redirect (e.g. ``maz.wifi`` → ``captive.ispman.tech``)
supports some inferences very strongly ("the portal uses ISPMan") but
NOT others ("ISPMan operates the Wi-Fi network", "Maz resells upstream
bandwidth"). The detector below encodes that asymmetry explicitly.

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
from portallens.portal import PortalRelationship, RelationshipKind

if TYPE_CHECKING:
    from portallens.plugins.captive_wifi.url_parser import CaptivePortalURLHints


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
    first. Relationships below 20% are dropped — below that the
    evidence is too thin to publish even as a hypothesis.
    """

    inferences: list[RelationshipInference] = []

    primary_host = hints.parsed.host.lower()

    # ------------------------------------------------------------------
    # 1. Build the redirect graph from link-login evidence.
    # ------------------------------------------------------------------
    # MikroTik's `link-login` parameter on the external portal URL
    # points back at the hotspot's login page (e.g. ISPMan's URL has
    # `link-login=http://maz.wifi/login?...`). That means the URL
    # carrying the parameter is the redirect TARGET, and the host the
    # parameter points at is the redirect SOURCE.
    #
    # We deliberately do NOT use `link-orig` here — that parameter is
    # the URL the user was originally trying to reach (e.g.
    # http://www.msftconnecttest.com/redirect for Apple's captive
    # probe), not a portal redirect.
    redirects: list[tuple[str, str, list[str]]] = []  # (source, target, evidence_ids)
    for ev in evidence:
        if ev.type is not EvidenceType.URL_PARAMETER:
            continue
        if ev.key not in {"link-login", "link-login-only"}:
            continue
        param_value = ev.value
        source_host = (urlparse(param_value).hostname or "").lower()
        target_host = (urlparse(ev.source).hostname or "").lower()
        if source_host and target_host and source_host != target_host:
            redirects.append((source_host, target_host, [ev.id]))

    # Also capture URL_REDIRECT evidence records — but only those the
    # analyzer recorded from `link-login` extraction (not `link-orig`).
    # The analyzer's evidence records carry the key `link_login_target`
    # for these, which we filter on.
    for ev in evidence:
        if ev.type is not EvidenceType.URL_REDIRECT:
            continue
        if ev.key != "link_login_target":
            continue
        param_value = ev.value
        source_host = (urlparse(param_value).hostname or "").lower()
        target_host = (urlparse(ev.source).hostname or "").lower()
        if source_host and target_host and source_host != target_host:
            redirects.append((source_host, target_host, [ev.id]))

    # Deduplicate by (source, target) — collect all evidence ids for each pair.
    redirect_pairs: dict[tuple[str, str], list[str]] = {}
    for source, target, ev_ids in redirects:
        key = (source, target)
        if key not in redirect_pairs:
            redirect_pairs[key] = []
        redirect_pairs[key].extend(ev_ids)

    # ------------------------------------------------------------------
    # 2. Emit REDIRECTS_TO relationships — high confidence for observed
    #    redirect evidence.
    # ------------------------------------------------------------------
    for (source, target), ev_ids in redirect_pairs.items():
        # Base weight per evidence record. Multiple link-* parameters
        # pointing the same direction reinforce each other.
        weights: list[int] = []
        for _ in ev_ids:
            weights.append(50)
        confidence = score(weights)
        if confidence.value >= 20:
            inferences.append(
                RelationshipInference(
                    kind=RelationshipKind.REDIRECTS_TO,
                    other=f"{source} → {target}",
                    confidence=confidence.value,
                    evidence_ids=ev_ids,
                    note=f"`{source}` redirects to `{target}` (observed via MikroTik link-* parameter on the target URL).",
                )
            )

    # ------------------------------------------------------------------
    # 3. USES_PLATFORM + AUTHENTICATES_FOR — if a redirect target is
    #    ISPMan, the source operator uses ISPMan as its platform.
    # ------------------------------------------------------------------
    from portallens.plugins.captive_wifi.url_parser import CaptivePortalFlavor

    ispman_redirects = [
        (s, t, eids) for (s, t), eids in redirect_pairs.items()
        if t == "ispman.tech" or t.endswith(".ispman.tech")
    ]
    # Also handle the case where the primary URL itself is ISPMan —
    # then we need to look at the redirects in the other direction.
    if CaptivePortalFlavor.ISPMAN in hints.flavors:
        for (source, target), eids in redirect_pairs.items():
            if target == primary_host and (source != "ispman.tech" and not source.endswith(".ispman.tech")):
                ispman_redirects.append((source, target, eids))

    for source, _target, ev_ids in ispman_redirects:
        # USES_PLATFORM: source uses ISPMan as platform.
        uses_confidence = score([60, 50])  # redirect + ISPMan host fingerprint
        inferences.append(
            RelationshipInference(
                kind=RelationshipKind.USES_PLATFORM,
                other=f"{source} → ISPMan",
                confidence=uses_confidence.value,
                evidence_ids=ev_ids,
                note=f"`{source}` operates a captive portal that uses ISPMan as its platform/backend.",
            )
        )
        # AUTHENTICATES_FOR: ISPMan authenticates for source.
        auth_confidence = score([75])
        inferences.append(
            RelationshipInference(
                kind=RelationshipKind.AUTHENTICATES_FOR,
                other=f"ISPMan → {source}",
                confidence=auth_confidence.value,
                evidence_ids=ev_ids,
                note=f"ISPMan captive portal handles authentication for `{source}`'s hotspot.",
            )
        )

    # ------------------------------------------------------------------
    # 4. OPERATES_NETWORK — local-only hostnames that serve captive
    #    portals are likely the network operator.
    # ------------------------------------------------------------------
    all_hosts: set[str] = set()
    for url in all_urls:
        h = (urlparse(url).hostname or "").lower()
        if h:
            all_hosts.add(h)
    for ev in evidence:
        if ev.type is EvidenceType.URL_HOST:
            all_hosts.add(ev.value.lower())

    for host in all_hosts:
        if host == "ispman.tech" or host.endswith(".ispman.tech"):
            continue
        # Local-only TLDs: .wifi, .local, or single-label hostnames.
        is_local_tld = (
            host.endswith(".wifi")
            or host.endswith(".local")
            or "." not in host
        )
        if not is_local_tld:
            continue
        # Evidence: URL_HOST records for this host.
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
    # 5. RESELLS_BANDWIDTH — explicitly low confidence without more
    #    evidence. We can speculate but we can't confirm. Capped at 35.
    # ------------------------------------------------------------------
    # Find local hosts that have a redirect to ISPMan.
    local_hosts_redirecting_to_ispman: set[str] = set()
    for (source, target), _ in redirect_pairs.items():
        if target == "ispman.tech" or target.endswith(".ispman.tech"):
            local_hosts_redirecting_to_ispman.add(source)

    for local_host in local_hosts_redirecting_to_ispman:
        ev_ids = [
            ev.id for ev in evidence
            if ev.type is EvidenceType.URL_REDIRECT
            and ev.key == "link_login_target"
            and "ispman" in ev.source.lower()
        ]
        ev_ids.extend(
            ev.id for ev in evidence
            if ev.type is EvidenceType.URL_PARAMETER
            and ev.key in {"link-login", "link-login-only"}
            and (
                (urlparse(ev.source).hostname or "").lower() == "ispman.tech"
                or (urlparse(ev.source).hostname or "").lower().endswith(".ispman.tech")
            )
        )
        confidence = score([35])
        inferences.append(
            RelationshipInference(
                kind=RelationshipKind.RESELLS_BANDWIDTH,
                other=f"{local_host} resells upstream bandwidth",
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
    # 6. Convert to PortalRelationship and drop <20 confidence.
    # ------------------------------------------------------------------
    out: list[PortalRelationship] = []
    for inf in inferences:
        if inf.confidence < 20:
            continue
        out.append(
            PortalRelationship(
                kind=inf.kind,
                other=inf.other,
                confidence=inf.confidence,
                evidence_ids=inf.evidence_ids,
                note=inf.note,
            )
        )
    out.sort(key=lambda r: -r.confidence)
    return out
