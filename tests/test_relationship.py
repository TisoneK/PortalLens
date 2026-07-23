"""Tests for the relationship inference module."""

from __future__ import annotations

from portallens.evidence import Evidence, EvidenceType
from portallens.plugins.captive_wifi.relationship import infer_relationships
from portallens.plugins.captive_wifi.url_parser import parse_captive_url
from portallens.portal import RelationshipKind
from tests.data import ISPMAN_URL, MAZ_URL


def _evidence_for_url(url: str) -> list[Evidence]:
    """Same evidence capture as the analyzer, for unit testing."""

    hints = parse_captive_url(url)
    out: list[Evidence] = []
    if hints.parsed.host:
        out.append(
            Evidence(
                type=EvidenceType.URL_HOST,
                source=url,
                key="host",
                value=hints.parsed.host,
            )
        )
    if hints.parsed.path and hints.parsed.path != "/":
        out.append(
            Evidence(
                type=EvidenceType.URL_PATH,
                source=url,
                key="path",
                value=hints.parsed.path,
            )
        )
    for k, v in hints.parsed.query_params:
        out.append(
            Evidence(
                type=EvidenceType.URL_PARAMETER,
                source=url,
                key=k,
                value=v,
            )
        )
    # Capture redirect evidence from MikroTik link-login / link-orig.
    if hints.mikrotik_link_login:
        from urllib.parse import urlparse

        target_host = (urlparse(hints.mikrotik_link_login).hostname or "").lower()
        primary_host = hints.parsed.host.lower()
        if target_host and target_host != primary_host:
            out.append(
                Evidence(
                    type=EvidenceType.URL_REDIRECT,
                    source=url,
                    key="link_login_target",
                    value=hints.mikrotik_link_login,
                )
            )
    return out


class TestIspmanRelationships:
    """When the user supplies both maz.wifi and captive.ispman.tech URLs."""

    def test_detects_redirects_to_ispman(self) -> None:
        # The primary URL is maz.wifi; the relationship should infer
        # that maz.wifi redirects to captive.ispman.tech.
        # We pass ISPMAN_URL as primary (it's the one with the full
        # query-string signature) but include MAZ_URL in all_urls so
        # the analyzer sees the local captive hostname.
        hints = parse_captive_url(ISPMAN_URL)
        ev = _evidence_for_url(ISPMAN_URL)
        rels = infer_relationships(hints, ev, [ISPMAN_URL, MAZ_URL])

        redirects_to_ispman = [
            r for r in rels
            if r.kind is RelationshipKind.REDIRECTS_TO and "ispman" in r.other
        ]
        assert redirects_to_ispman, "expected a REDIRECTS_TO relationship to ispman.tech"

    def test_detects_uses_platform_relationship(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        ev = _evidence_for_url(ISPMAN_URL)
        rels = infer_relationships(hints, ev, [ISPMAN_URL, MAZ_URL])

        uses_platform = [r for r in rels if r.kind is RelationshipKind.USES_PLATFORM]
        assert uses_platform
        assert any("maz.wifi" in r.other and "ISPMan" in r.other for r in uses_platform)

    def test_detects_authenticates_for_relationship(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        ev = _evidence_for_url(ISPMAN_URL)
        rels = infer_relationships(hints, ev, [ISPMAN_URL, MAZ_URL])

        auth = [r for r in rels if r.kind is RelationshipKind.AUTHENTICATES_FOR]
        assert auth
        assert any("ISPMan" in r.other and "maz.wifi" in r.other for r in auth)
        # Authenticates-for is a strong inference — should be ≥ 60.
        assert auth[0].confidence >= 60

    def test_detects_operates_network_relationship(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        ev = _evidence_for_url(ISPMAN_URL)
        rels = infer_relationships(hints, ev, [ISPMAN_URL, MAZ_URL])

        operates = [r for r in rels if r.kind is RelationshipKind.OPERATES_NETWORK]
        assert operates
        assert any("maz.wifi" in r.other for r in operates)

    def test_resells_bandwidth_is_low_confidence(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        ev = _evidence_for_url(ISPMAN_URL)
        rels = infer_relationships(hints, ev, [ISPMAN_URL, MAZ_URL])

        resells = [r for r in rels if r.kind is RelationshipKind.RESELLS_BANDWIDTH]
        assert resells
        # Resells-bandwidth is explicitly capped at low confidence —
        # the URL alone cannot distinguish reseller from operator.
        assert resells[0].confidence < 40
