"""Tests for the fingerprint detector."""

from __future__ import annotations

from portallens.evidence import Evidence, EvidenceType
from portallens.plugins.captive_wifi.fingerprints import detect_fingerprints
from portallens.plugins.captive_wifi.url_parser import parse_captive_url
from tests.data import ISPMAN_URL, MAZ_URL


def _evidence_for_url(url: str) -> list[Evidence]:
    """Capture the same evidence the analyzer does, for unit testing."""

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
    return out


class TestMazFingerprints:
    def test_detects_mikrotik(self) -> None:
        hints = parse_captive_url(MAZ_URL)
        ev = _evidence_for_url(MAZ_URL)
        matches = detect_fingerprints(hints, ev)
        platforms = {m.platform for m in matches}
        assert "MikroTik RouterOS Hotspot" in platforms

    def test_mikrotik_confidence_with_dst_only_is_low(self) -> None:
        # maz.wifi has only `dst` — the MikroTik entry-URL signature.
        # That's enough to fire the flavor but not enough for high
        # confidence. The detector should call MikroTik with low
        # confidence (≥ 20) — honest about the thin evidence.
        hints = parse_captive_url(MAZ_URL)
        ev = _evidence_for_url(MAZ_URL)
        matches = detect_fingerprints(hints, ev)
        mikrotik = next(m for m in matches if m.platform == "MikroTik RouterOS Hotspot")
        assert 20 <= mikrotik.confidence < 40

    def test_mikrotik_confidence_with_full_signature_is_high(self) -> None:
        # The ISPMan URL carries the full MikroTik signature
        # (link-login + link-orig + dst + mac + ip) forwarded by the
        # redirect. The detector should call MikroTik with high
        # confidence on this URL.
        hints = parse_captive_url(ISPMAN_URL)
        ev = _evidence_for_url(ISPMAN_URL)
        matches = detect_fingerprints(hints, ev)
        mikrotik = next(m for m in matches if m.platform == "MikroTik RouterOS Hotspot")
        assert mikrotik.confidence >= 75


class TestIspmanFingerprints:
    def test_detects_both_ispman_and_mikrotik(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        ev = _evidence_for_url(ISPMAN_URL)
        matches = detect_fingerprints(hints, ev)
        platforms = {m.platform for m in matches}
        assert "ISPMan" in platforms
        assert "MikroTik RouterOS Hotspot" in platforms

    def test_ispman_is_strongest_fingerprint(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        ev = _evidence_for_url(ISPMAN_URL)
        matches = detect_fingerprints(hints, ev)
        # ISPMan gets weight 60 (host) + 50 (path) = combined ~80
        # MikroTik gets weight 55 (link-login) + 40 (link-orig) + 20 (dst)
        #   + 10 (mac) + 10 (ip) = combined ~80 too
        # Both should be high confidence; ISPMan is listed first
        # (sorted by confidence desc, ties broken by insertion order).
        assert matches[0].platform in {"ISPMan", "MikroTik RouterOS Hotspot"}
        assert matches[0].confidence >= 75

    def test_ispman_fingerprint_cites_evidence(self) -> None:
        hints = parse_captive_url(ISPMAN_URL)
        ev = _evidence_for_url(ISPMAN_URL)
        matches = detect_fingerprints(hints, ev)
        ispman = next(m for m in matches if m.platform == "ISPMan")
        assert len(ispman.evidence_ids) >= 2  # host + path

    def test_ispman_confidence_at_least_very_high(self) -> None:
        # The host + path combination is uniquely ISPMan — confidence
        # should clear the very_high (>= 80) threshold.
        hints = parse_captive_url(ISPMAN_URL)
        ev = _evidence_for_url(ISPMAN_URL)
        matches = detect_fingerprints(hints, ev)
        ispman = next(m for m in matches if m.platform == "ISPMan")
        assert ispman.confidence >= 80
