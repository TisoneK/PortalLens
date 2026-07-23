"""Tests for the signature registry.

These are the tests that keep the analyzer from drifting back to being
centered on one provider. They assert three things:

1. Registry invariants hold (unique slugs, hosted platforms own hostnames,
   no "original destination" parameter is treated as a redirect).
2. A provider other than the one the analyzer was first written against gets
   the same reasoning — fingerprint, ``USES_PLATFORM``, ``AUTHENTICATES_FOR``.
3. A provider that exists only as a registry entry, added at runtime, is
   picked up end to end without any detector change.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from portallens.evidence import Evidence, EvidenceType, reset_evidence_ids
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.plugins.captive_wifi import fingerprints as fingerprints_mod
from portallens.plugins.captive_wifi import signatures as signatures_mod
from portallens.plugins.captive_wifi import url_parser as url_parser_mod
from portallens.plugins.captive_wifi.relationship import infer_relationships
from portallens.plugins.captive_wifi.signatures import (
    SIGNATURES,
    PortalSignature,
    Provenance,
    SignatureLayer,
    SignatureRule,
    platform_for_host,
)
from portallens.plugins.captive_wifi.url_parser import parse_captive_url
from portallens.portal import AnalysisContext, RelationshipKind

# A MikroTik hotspot whose portal is hosted by Cisco Meraki rather than
# ISPMan. Synthetic, but built from the same shape as the real fixture: the
# gateway's link-login points back at the local hostname.
MERAKI_URL = (
    "https://n143.network-auth.com/splash/index.html"
    "?mac=04%3AED%3A33%3A76%3AD9%3AA0"
    "&ip=10.0.0.7"
    "&link-login=http%3A%2F%2Fguest.lan%2Flogin"
    "&link-orig=http%3A%2F%2Fwww.msftconnecttest.com%2Fredirect"
)
LOCAL_GATEWAY_URL = "http://guest.lan/login?dst=http%3A%2F%2Fexample.com%2F"


def _evidence_for(url: str) -> list[Evidence]:
    """The analyzer's evidence capture, reduced to what these tests need."""

    hints = parse_captive_url(url)
    out: list[Evidence] = [
        Evidence(type=EvidenceType.URL_HOST, source=url, key="host", value=hints.parsed.host)
    ]
    if hints.parsed.path and hints.parsed.path != "/":
        out.append(
            Evidence(type=EvidenceType.URL_PATH, source=url, key="path", value=hints.parsed.path)
        )
    out.extend(
        Evidence(type=EvidenceType.URL_PARAMETER, source=url, key=k, value=v)
        for k, v in hints.parsed.query_params
    )
    for gateway in hints.gateways:
        for key in sorted(gateway.backlink_params):
            value = hints.parsed.param(key)
            if not value:
                continue
            if (urlparse(value).hostname or "").lower() != hints.parsed.host.lower():
                out.append(
                    Evidence(
                        type=EvidenceType.URL_REDIRECT,
                        source=url,
                        key="link_login_target",
                        value=value,
                    )
                )
                break
    return out


class TestRegistryInvariants:
    def test_slugs_are_unique(self) -> None:
        slugs = [s.slug for s in SIGNATURES]
        assert len(slugs) == len(set(slugs))

    def test_hosted_platforms_own_a_hostname(self) -> None:
        # A hosted platform is identified BY its hostname — without one,
        # relationship inference cannot tell it apart from the operator.
        for signature in SIGNATURES:
            if signature.is_hosted_platform:
                assert signature.host_suffixes, f"{signature.slug} declares no host suffix"

    def test_gateways_own_no_hostname(self) -> None:
        # A gateway runs on whatever hostname the local operator chose.
        for signature in SIGNATURES:
            if signature.layer is SignatureLayer.GATEWAY:
                assert not signature.host_suffixes, f"{signature.slug} claims a hostname"

    def test_original_destination_params_are_never_backlinks(self) -> None:
        # `link-orig` / `userurl` name the site the client was loading when it
        # got captured. Treating either as a portal redirect invents
        # relationships to unrelated third parties.
        for signature in SIGNATURES:
            assert not (signature.backlink_params & {"link-orig", "userurl"})

    def test_every_signature_declares_provenance_and_a_note(self) -> None:
        for signature in SIGNATURES:
            assert signature.note
            assert isinstance(signature.provenance, Provenance)


class TestHostMatching:
    def test_matches_exact_host(self) -> None:
        assert platform_for_host("ispman.tech") is not None

    def test_matches_subdomain(self) -> None:
        platform = platform_for_host("captive.ispman.tech")
        assert platform is not None and platform.slug == "ispman"

    def test_does_not_match_lookalike_suffix(self) -> None:
        # Suffix matching is on label boundaries — otherwise an attacker
        # registering `evilispman.tech` would be reported as ISPMan.
        assert platform_for_host("evilispman.tech") is None

    def test_does_not_match_unrelated_host(self) -> None:
        assert platform_for_host("example.com") is None

    def test_empty_host_is_not_a_platform(self) -> None:
        assert platform_for_host("") is None


class TestSignaturesDoNotOverreach:
    """Signatures keyed on generic parameter names must require their path.

    UniFi's guest portal passes `id`, `ap`, and `url` — names common enough
    that matching on them alone would fire on half the web.
    """

    def test_unifi_matches_on_its_path(self) -> None:
        hints = parse_captive_url("https://unifi.example.com/guest/s/default/?id=aabbcc&ap=112233")
        assert "unifi" in hints.flavors

    def test_unifi_does_not_match_a_bare_id_parameter(self) -> None:
        hints = parse_captive_url("https://shop.example.com/products?id=aabbcc")
        assert hints.is_generic

    def test_meraki_does_not_match_its_host_without_the_splash_path(self) -> None:
        hints = parse_captive_url("https://n143.network-auth.com/status")
        assert hints.platform is None


class TestSecondProvider:
    """The analyzer must reason about Meraki exactly as it does about ISPMan."""

    def test_detects_meraki_platform(self) -> None:
        hints = parse_captive_url(MERAKI_URL)
        assert hints.platform is not None
        assert hints.platform.slug == "meraki"

    def test_detects_the_gateway_behind_it(self) -> None:
        hints = parse_captive_url(MERAKI_URL)
        assert "mikrotik" in hints.flavors

    def test_fingerprints_name_meraki(self) -> None:
        hints = parse_captive_url(MERAKI_URL)
        matches = fingerprints_mod.detect_fingerprints(hints, _evidence_for(MERAKI_URL))
        assert any(m.platform == "Cisco Meraki Splash" for m in matches)

    def test_unvalidated_signature_says_so_in_its_note(self) -> None:
        hints = parse_captive_url(MERAKI_URL)
        matches = fingerprints_mod.detect_fingerprints(hints, _evidence_for(MERAKI_URL))
        meraki = next(m for m in matches if m.platform == "Cisco Meraki Splash")
        assert meraki.note is not None
        assert "not yet validated" in meraki.note

    def test_infers_uses_platform_for_meraki(self) -> None:
        hints = parse_captive_url(MERAKI_URL)
        rels = infer_relationships(hints, _evidence_for(MERAKI_URL), [MERAKI_URL, LOCAL_GATEWAY_URL])
        uses = [r for r in rels if r.kind is RelationshipKind.USES_PLATFORM]
        assert uses
        assert any("guest.lan" in r.other and "Meraki" in r.other for r in uses)

    def test_infers_authenticates_for_meraki(self) -> None:
        hints = parse_captive_url(MERAKI_URL)
        rels = infer_relationships(hints, _evidence_for(MERAKI_URL), [MERAKI_URL, LOCAL_GATEWAY_URL])
        auth = [r for r in rels if r.kind is RelationshipKind.AUTHENTICATES_FOR]
        assert auth
        assert any("Meraki" in r.other and "guest.lan" in r.other for r in auth)

    def test_platform_host_is_not_reported_as_network_operator(self) -> None:
        hints = parse_captive_url(MERAKI_URL)
        rels = infer_relationships(hints, _evidence_for(MERAKI_URL), [MERAKI_URL, LOCAL_GATEWAY_URL])
        operates = [r for r in rels if r.kind is RelationshipKind.OPERATES_NETWORK]
        assert all("network-auth.com" not in r.other for r in operates)


class TestNoDuplicateRelationships:
    """Regression: the pre-registry analyzer emitted USES_PLATFORM and
    AUTHENTICATES_FOR twice for the same pair — once from the redirect scan
    and once from the "the primary URL is the platform" branch."""

    def setup_method(self) -> None:
        reset_evidence_ids()

    def test_each_relationship_appears_once(self) -> None:
        from tests.data import ISPMAN_URL, MAZ_URL

        report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        seen = [(r.kind, r.other) for r in report.relationships]
        assert len(seen) == len(set(seen)), f"duplicate relationships: {seen}"


class TestRuntimeRegisteredProvider:
    """Adding a provider must be a registry entry, not a code change.

    This test registers a provider that exists nowhere in the source tree and
    asserts the detectors pick it up unchanged.
    """

    @pytest.fixture
    def registered(self, monkeypatch: pytest.MonkeyPatch) -> PortalSignature:
        invented = PortalSignature(
            slug="acmeportal",
            platform="Acme Portal",
            layer=SignatureLayer.HOSTED_PLATFORM,
            rules=(
                SignatureRule(host_suffixes=("acme-portals.example",), path_prefixes=("/p/",)),
            ),
            host_suffixes=("acme-portals.example",),
            host_weight=60,
            path_weight=50,
            note="Test-only signature.",
        )
        extended = (*SIGNATURES, invented)
        # Patch every module that bound the registry at import time.
        monkeypatch.setattr(signatures_mod, "SIGNATURES", extended)
        monkeypatch.setattr(url_parser_mod, "SIGNATURES", extended)
        monkeypatch.setattr(fingerprints_mod, "SIGNATURES", extended)
        monkeypatch.setattr(
            signatures_mod,
            "HOSTED_PLATFORM_SIGNATURES",
            (*signatures_mod.HOSTED_PLATFORM_SIGNATURES, invented),
        )
        return invented

    def test_url_parser_picks_it_up(self, registered: PortalSignature) -> None:
        hints = parse_captive_url("https://portal.acme-portals.example/p/login?mac=aa")
        assert hints.platform is not None
        assert hints.platform.slug == "acmeportal"

    def test_fingerprint_detector_scores_it(self, registered: PortalSignature) -> None:
        url = "https://portal.acme-portals.example/p/login?mac=aa"
        hints = parse_captive_url(url)
        matches = fingerprints_mod.detect_fingerprints(hints, _evidence_for(url))
        acme = next(m for m in matches if m.platform == "Acme Portal")
        # Host (60) + path (50) combined by noisy-OR, same as any other
        # hosted platform.
        assert acme.confidence == 80

    def test_relationship_inference_names_it(self, registered: PortalSignature) -> None:
        url = (
            "https://portal.acme-portals.example/p/login"
            "?mac=aa&link-login=http%3A%2F%2Fhotel.lan%2Flogin"
            "&link-orig=http%3A%2F%2Fexample.com%2F"
        )
        hints = parse_captive_url(url)
        rels = infer_relationships(hints, _evidence_for(url), [url])
        uses = [r for r in rels if r.kind is RelationshipKind.USES_PLATFORM]
        assert any("hotel.lan" in r.other and "Acme Portal" in r.other for r in uses)
