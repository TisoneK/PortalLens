"""Tests for bounded captive-portal connectivity detection."""

from __future__ import annotations

import pytest

from portallens.acquisition import AcquisitionDenied
from portallens.evidence import EvidenceType
from portallens.portal import AcquisitionPolicy
from portallens.wifi import (
    CancellationToken,
    WifiConnection,
    WifiConnectionState,
    WifiNetwork,
    WifiSecurity,
)
from portallens.wifi.captive_portal import (
    ANDROID_CLIENTS3_GENERATE_204,
    ANDROID_GENERATE_204,
    APPLE_HOTSPOT,
    WINDOWS_NCSI,
    CaptivePortalDetector,
    CaptivePortalProbeProfile,
    CaptivePortalProbeResult,
    CaptivePortalResponse,
    WifiProbePlatform,
    analyze_probe_result,
    apply_probe_result,
    parse_captive_portal_metadata,
    profiles_for_platform,
)
from portallens.wifi.errors import WifiOperationCancelled

AUTHORIZED = AcquisitionPolicy(authorized=True)


def _response(
    status_code: int,
    *,
    body: str = "",
    location: str | None = None,
    body_truncated: bool = False,
    content_type: str = "text/plain",
) -> CaptivePortalResponse:
    headers = {"content-type": content_type}
    if location is not None:
        headers["location"] = location
    return CaptivePortalResponse(
        status_code=status_code,
        headers=headers,
        body=body,
        body_truncated=body_truncated,
    )


def _detector(response: CaptivePortalResponse, calls: list[tuple[str, dict[str, str], int]]) -> CaptivePortalDetector:
    def request(url, headers, cancel, timeout, max_body_bytes):
        calls.append((url, dict(headers), max_body_bytes))
        cancel.raise_if_cancelled()
        return response

    return CaptivePortalDetector(request=request, max_body_bytes=32)


class TestProbeProfiles:
    def test_profiles_use_fixed_platform_endpoints(self) -> None:
        assert WINDOWS_NCSI.url == "http://www.msftncsi.com/ncsi.txt"
        assert ANDROID_GENERATE_204.expected_statuses == (204,)
        assert ANDROID_CLIENTS3_GENERATE_204.url == "http://clients3.google.com/generate_204"
        assert profiles_for_platform(WifiProbePlatform.APPLE) == (APPLE_HOTSPOT,)
        assert profiles_for_platform("windows")

    def test_arbitrary_profile_is_rejected_before_request(self) -> None:
        calls = []
        detector = _detector(_response(204), calls)
        arbitrary = CaptivePortalProbeProfile(
            name="arbitrary",
            platform=WifiProbePlatform.ANDROID,
            url="http://127.0.0.1:8080/internal",
            expected_statuses=(204,),
        )
        with pytest.raises(ValueError, match="built-in profile"):
            detector.probe(arbitrary, AUTHORIZED)
        assert calls == []

    def test_unauthorized_probe_is_rejected_before_request(self) -> None:
        calls = []
        detector = _detector(_response(204), calls)
        with pytest.raises(AcquisitionDenied, match="authorized"):
            detector.probe(ANDROID_GENERATE_204, AcquisitionPolicy())
        assert calls == []


class TestLegacyProbe:
    def test_expected_android_204_is_unrestricted(self) -> None:
        calls = []
        result = _detector(_response(204), calls).probe(ANDROID_GENERATE_204, AUTHORIZED)
        assert result.captive is False
        assert result.status_code == 204
        assert result.portal_url is None
        assert any(ev.key == "probe:classification" and ev.value == "unrestricted" for ev in result.evidence)
        assert calls[0][0] == ANDROID_GENERATE_204.url

    def test_redirect_is_captured_without_following(self) -> None:
        calls = []
        result = _detector(
            _response(
                302,
                location="http://portal.example/login?token=secret-value&dst=https%3A%2F%2Fexample.com",
            ),
            calls,
        ).probe(ANDROID_GENERATE_204, AUTHORIZED)
        assert result.captive is True
        assert result.portal_url == "http://portal.example/login?token=%5BREDACTED%5D&dst=https%3A%2F%2Fexample.com"
        assert all(ev.value != "secret-value" for ev in result.evidence)
        assert len(calls) == 1

    def test_redirect_without_location_is_unknown(self) -> None:
        calls = []
        result = _detector(_response(302), calls).probe(ANDROID_GENERATE_204, AUTHORIZED)
        assert result.captive is None
        assert result.portal_url is None

    def test_expected_status_with_possible_portal_body_is_unconfirmed(self) -> None:
        calls = []
        result = _detector(_response(200, body="<html>login</html>"), calls).probe(
            APPLE_HOTSPOT, AUTHORIZED
        )
        assert result.captive is None
        assert result.portal_url is None

    def test_generic_error_body_is_unknown(self) -> None:
        calls = []
        result = _detector(_response(200, body="upstream error"), calls).probe(
            APPLE_HOTSPOT, AUTHORIZED
        )
        assert result.captive is None
        assert result.portal_url is None

    def test_capped_body_without_marker_is_unknown(self) -> None:
        calls = []
        result = _detector(
            _response(200, body="not the marker", body_truncated=True), calls
        ).probe(WINDOWS_NCSI, AUTHORIZED)
        assert result.captive is None
        assert result.body_truncated is True

    @pytest.mark.parametrize("status_code", [404, 500])
    def test_server_or_client_error_is_unknown_not_confirmed_captive(self, status_code: int) -> None:
        calls = []
        result = _detector(_response(status_code), calls).probe(WINDOWS_NCSI, AUTHORIZED)
        assert result.captive is None
        assert result.error is None

    def test_cancellation_is_propagated(self) -> None:
        token = CancellationToken()
        token.cancel()
        calls = []
        with pytest.raises(WifiOperationCancelled):
            _detector(_response(204), calls).probe(
                ANDROID_GENERATE_204, AUTHORIZED, cancel=token
            )
        assert calls == []


class TestRfc8908:
    def test_metadata_requires_boolean_and_redacts_sensitive_url_values(self) -> None:
        metadata = parse_captive_portal_metadata(
            '{"captive":true,"user-portal-url":"https://portal.example/login?token=secret",'
            '"venue-info-url":"https://venue.example/map","can-extend-session":true,'
            '"seconds-remaining":120,"bytes-remaining":4096}'
        )
        assert metadata.captive is True
        assert metadata.user_portal_url == "https://portal.example/login?token=%5BREDACTED%5D"
        assert metadata.venue_info_url == "https://venue.example/map"
        assert metadata.seconds_remaining == 120

    @pytest.mark.parametrize(
        "payload",
        [
            "{}",
            '{"captive":"yes"}',
            '{"captive":true,"user-portal-url":"http://portal.example"}',
            '{"captive":true,"can-extend-session":"yes"}',
        ],
    )
    def test_metadata_rejects_invalid_shapes(self, payload: str) -> None:
        with pytest.raises(ValueError):
            parse_captive_portal_metadata(payload)

    def test_captive_metadata_produces_portal_url_and_accept_header(self) -> None:
        calls = []
        body = '{"captive":true,"user-portal-url":"https://portal.example/login?state=opaque"}'
        result = _detector(
            _response(200, body=body, content_type="application/captive+json"), calls
        ).probe_rfc8908(
            "https://capport.example/api?token=hidden", AUTHORIZED, provisioned=True
        )
        assert result.captive is True
        assert result.portal_url == "https://portal.example/login?state=%5BREDACTED%5D"
        assert calls[0][1]["Accept"] == "application/captive+json"
        assert calls[0][0] == "https://capport.example/api?token=hidden"

    def test_unrestricted_metadata_has_no_portal_url(self) -> None:
        calls = []
        result = _detector(
            _response(200, body='{"captive":false}', content_type="application/captive+json"), calls
        ).probe_rfc8908(
            "https://capport.example/api", AUTHORIZED, provisioned=True
        )
        assert result.captive is False
        assert result.portal_url is None

    def test_rfc_endpoint_must_be_https_and_provisioned(self) -> None:
        calls = []
        with pytest.raises(ValueError, match="HTTPS"):
            _detector(_response(200, body='{"captive":false}'), calls).probe_rfc8908(
                "http://capport.example/api", AUTHORIZED
            )
        with pytest.raises(ValueError, match="explicitly provisioned"):
            _detector(_response(200, body='{"captive":false}'), calls).probe_rfc8908(
                "https://capport.example/api", AUTHORIZED
            )
        assert calls == []


class TestIntegrationSeams:
    def test_apply_probe_result_transitions_ip_configured_connection(self) -> None:
        network = WifiNetwork(ssid="Guest", security=WifiSecurity.OPEN, interface="en0")
        connection = WifiConnection(network=network, state=WifiConnectionState.IP_CONFIGURED)
        result = CaptivePortalProbeResult(
            profile_name="fixture",
            probe_url="http://probe.example/check",
            captive=True,
            status_code=302,
            portal_url="http://portal.example/login",
        )
        updated = apply_probe_result(connection, result)
        assert updated.state is WifiConnectionState.CAPTIVE_PORTAL
        assert updated.portal_url == "http://portal.example/login"

    def test_apply_probe_result_redacts_manual_portal_url(self) -> None:
        network = WifiNetwork(ssid="Guest", security=WifiSecurity.OPEN, interface="en0")
        connection = WifiConnection(network=network, state=WifiConnectionState.IP_CONFIGURED)
        result = CaptivePortalProbeResult(
            profile_name="fixture",
            probe_url="http://probe.example/check",
            captive=True,
            status_code=302,
            portal_url="http://portal.example/login?token=secret",
        )
        updated = apply_probe_result(connection, result)
        assert updated.portal_url == "http://portal.example/login?token=%5BREDACTED%5D"

    def test_repeated_captive_detection_is_idempotent(self) -> None:
        network = WifiNetwork(ssid="Guest", security=WifiSecurity.OPEN, interface="en0")
        connection = WifiConnection(
            network=network,
            state=WifiConnectionState.CAPTIVE_PORTAL,
            portal_url="http://portal.example/login",
        )
        result = CaptivePortalProbeResult(
            profile_name="fixture",
            probe_url="http://probe.example/check",
            captive=True,
            status_code=302,
            portal_url="http://portal.example/login",
        )
        assert apply_probe_result(connection, result) is connection

    def test_apply_unrestricted_result_transitions_online(self) -> None:
        network = WifiNetwork(ssid="Guest", security=WifiSecurity.OPEN, interface="en0")
        connection = WifiConnection(network=network, state=WifiConnectionState.IP_CONFIGURED)
        result = CaptivePortalProbeResult(
            profile_name="fixture",
            probe_url="http://probe.example/check",
            captive=False,
            status_code=204,
        )
        assert apply_probe_result(connection, result).state is WifiConnectionState.ONLINE

    def test_apply_unknown_result_does_not_change_connection(self) -> None:
        network = WifiNetwork(ssid="Guest", security=WifiSecurity.OPEN, interface="en0")
        connection = WifiConnection(network=network, state=WifiConnectionState.IP_CONFIGURED)
        result = CaptivePortalProbeResult(
            profile_name="fixture",
            probe_url="http://probe.example/check",
            captive=None,
            status_code=None,
        )
        assert apply_probe_result(connection, result) is connection

    def test_analyzer_handoff_redacts_manual_portal_url(self) -> None:
        result = CaptivePortalProbeResult(
            profile_name="fixture",
            probe_url="http://probe.example/check",
            captive=True,
            status_code=302,
            portal_url="http://portal.example/login?token=secret",
        )
        report = analyze_probe_result(result)
        assert report.primary_url == "http://portal.example/login?token=%5BREDACTED%5D"

    def test_unrestricted_result_cannot_be_handed_to_analyzer(self) -> None:
        result = CaptivePortalProbeResult(
            profile_name="fixture",
            probe_url="http://probe.example/check",
            captive=False,
            status_code=204,
            portal_url="http://portal.example/login",
        )
        with pytest.raises(ValueError, match="confirm captivity"):
            result.analysis_context()

    def test_analyzer_handoff_is_passive_and_uses_detected_url(self) -> None:
        result = CaptivePortalProbeResult(
            profile_name="fixture",
            probe_url="http://probe.example/check",
            captive=True,
            status_code=302,
            portal_url="http://portal.example/login?dst=https%3A%2F%2Fexample.com",
        )
        report = analyze_probe_result(result, notes="captured by fixture")
        assert report.primary_url == result.portal_url
        assert report.evidence

    def test_evidence_is_typed(self) -> None:
        calls = []
        result = _detector(_response(204), calls).probe(ANDROID_GENERATE_204, AUTHORIZED)
        assert all(ev.type is EvidenceType.CAPTIVE_PORTAL_STATUS for ev in result.evidence)
