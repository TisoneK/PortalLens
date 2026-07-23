"""Tests for the captive-portal URL parser."""

from __future__ import annotations

from portallens.plugins.captive_wifi.signatures import SignatureLayer
from portallens.plugins.captive_wifi.url_parser import (
    CaptivePortalFlavor,
    looks_like_captive_portal,
    parse_captive_url,
)
from tests.data import ISPMAN_URL, MAZ_URL


class TestMazUrl:
    """The local maz.wifi captive hostname — MikroTik signature."""

    def test_parses_without_error(self) -> None:
        parse_captive_url(MAZ_URL)

    def test_host_is_maz_wifi(self) -> None:
        hints = parse_captive_url(MAZ_URL)
        assert hints.parsed.host == "maz.wifi"

    def test_detects_mikrotik_flavor(self) -> None:
        hints = parse_captive_url(MAZ_URL)
        assert CaptivePortalFlavor.MIKROTIK in hints.flavors

    def test_extracts_dst_parameter(self) -> None:
        hints = parse_captive_url(MAZ_URL)
        assert hints.mikrotik_dst is not None
        assert "msftconnecttest.com" in hints.mikrotik_dst

    def test_looks_like_captive_portal(self) -> None:
        assert looks_like_captive_portal(MAZ_URL) is True


class TestIspmanUrl:
    """The external captive.ispman.tech URL — ISPMan + MikroTik signature."""

    def test_parses_without_error(self) -> None:
        parse_captive_url(ISPMAN_URL)

    def test_host_is_captive_ispman_tech(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        assert hints.parsed.host == "captive.ispman.tech"

    def test_detects_ispman_flavor(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        assert CaptivePortalFlavor.ISPMAN in hints.flavors

    def test_detects_mikrotik_flavor(self) -> None:
        # ISPMan receives the MikroTik-style query params via the
        # redirect — so the URL carries both signatures.
        hints = parse_captive_url(ISPMAN_URL)
        assert CaptivePortalFlavor.MIKROTIK in hints.flavors

    def test_identifies_the_hosted_platform(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        assert hints.platform is not None
        assert hints.platform.slug == "ispman"
        assert hints.platform.layer is SignatureLayer.HOSTED_PLATFORM

    def test_extracts_platform_path_ids(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        # The path is /hotspots/<id1>/<id2>/<id3>/<tier>/select — we
        # extract everything between /hotspots/ and /<tier>/select.
        assert len(hints.platform_path_ids) == 3
        assert hints.platform_path_ids[0] == "366ba450-bc93-4970-97d6-0585aa985a12"
        assert hints.platform_path_ids[1] == "381168ce-bbb2-4f86-8fb8-d6d48321d8bb"

    def test_extracts_link_login_pointing_at_maz(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        assert hints.mikrotik_link_login is not None
        assert "maz.wifi" in hints.mikrotik_link_login

    def test_extracts_mac_and_ip(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        assert hints.mikrotik_mac == "04:ED:33:76:D9:A0"
        assert hints.mikrotik_ip == "10.111.151.194"

    def test_looks_like_captive_portal(self) -> None:
        assert looks_like_captive_portal(ISPMAN_URL) is True


class TestNonCaptiveUrl:
    """A URL that doesn't match any captive-portal signature."""

    def test_generic_flavor_only(self) -> None:
        hints = parse_captive_url("https://example.com/some/page?foo=bar")
        assert hints.flavors == [CaptivePortalFlavor.GENERIC]

    def test_does_not_look_captive(self) -> None:
        assert looks_like_captive_portal("https://example.com/some/page?foo=bar") is False
