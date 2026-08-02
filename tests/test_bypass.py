"""Tests for bounded captive-portal bypass detection.

The tests inject network behavior so they never touch a live target. Positive
results mean only that a bounded detection condition was observed; they are
not treated as proof of unrestricted access.
"""

from __future__ import annotations

from urllib.parse import unquote

import pytest

from portallens.evidence import Evidence, EvidenceType, reset_evidence_ids
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.portal import AcquisitionPolicy, AnalysisContext, PortalReport
from portallens.security import (
    ConnectResult,
    ProbeResponse,
    click_through_test,
    connect_test,
    detect_bypass,
    dns_tunnel_test,
    merge_bypass_evidence,
    parameter_tampering_test,
    port_scan_test,
)
from tests.data import ISPMAN_URL, MAZ_URL

AUTHORIZED = AcquisitionPolicy(authorized=True)


class TestConnectTest:
    def test_requires_authorization(self) -> None:
        with pytest.raises(Exception, match="connect_test"):
            connect_test("proxy.local:8080", "https://example.com", AcquisitionPolicy())

    def test_records_allowed_tunnel_as_evidence(self) -> None:
        evidence = connect_test(
            "proxy.local:8080",
            "https://example.com",
            AUTHORIZED,
            connect_request=lambda proxy, target, timeout: ConnectResult(200, "Connection Established"),
        )
        assert len(evidence) == 1
        assert evidence[0].type is EvidenceType.BYPASS_CONNECT
        assert evidence[0].key == "connect:allowed"

    def test_records_blocked_tunnel_as_evidence(self) -> None:
        evidence = connect_test(
            "proxy.local:8080",
            "https://example.com",
            AUTHORIZED,
            connect_request=lambda proxy, target, timeout: ConnectResult(403, "Forbidden"),
        )
        assert evidence[0].key == "connect:blocked"


class TestDnsTunnelTest:
    def test_requires_authorization(self) -> None:
        with pytest.raises(Exception, match="dns_tunnel_test"):
            dns_tunnel_test("unique.example", AcquisitionPolicy())

    def test_normal_answer_is_possible_bypass_evidence(self) -> None:
        evidence = dns_tunnel_test(
            "unique.example",
            AUTHORIZED,
            resolve=lambda hostname: ["203.0.113.10"],
            captive_addresses=["192.0.2.1"],
        )
        assert evidence[0].type is EvidenceType.BYPASS_DNS
        assert evidence[0].key == "dns_tunnel:allowed"
        assert "203.0.113.10" in evidence[0].value

    def test_captive_answer_is_blocked_evidence(self) -> None:
        evidence = dns_tunnel_test(
            "unique.example",
            AUTHORIZED,
            resolve=lambda hostname: ["192.0.2.1"],
            captive_addresses=["192.0.2.1"],
        )
        assert evidence[0].key == "dns_tunnel:blocked"


class TestClickThroughTest:
    def test_requires_authorization(self) -> None:
        with pytest.raises(Exception, match="click_through_test"):
            click_through_test("https://example.com", "portal.local", AcquisitionPolicy())

    def test_reaching_target_is_possible_bypass_evidence(self) -> None:
        evidence = click_through_test(
            "https://example.com/health",
            "portal.local",
            AUTHORIZED,
            request=lambda url: ProbeResponse(200, "https://example.com/health"),
        )
        assert evidence[0].type is EvidenceType.BYPASS_CLICK_THROUGH
        assert evidence[0].key == "click_through:allowed"

    def test_portal_redirect_is_blocked_evidence(self) -> None:
        evidence = click_through_test(
            "https://example.com/health",
            "portal.local",
            AUTHORIZED,
            request=lambda url: ProbeResponse(302, "http://portal.local/login"),
        )
        assert evidence[0].key == "click_through:blocked"


class TestPortScanTest:
    def test_requires_authorization(self) -> None:
        with pytest.raises(Exception, match="bypass_port_scan"):
            port_scan_test("portal.local", AcquisitionPolicy(), ports=[80])

    def test_returns_bounded_open_and_closed_evidence(self) -> None:
        seen: list[int] = []

        def probe(host: str, port: int) -> bool:
            seen.append(port)
            return port == 443

        evidence = port_scan_test(
            "portal.local", AUTHORIZED, ports=[80, 443], probe_port=probe
        )
        assert seen == [80, 443]
        assert [item.key for item in evidence] == ["port_scan:closed", "port_scan:open"]
        assert all(item.type is EvidenceType.BYPASS_PORT for item in evidence)

    def test_rejects_unbounded_port_list(self) -> None:
        with pytest.raises(ValueError, match="at most"):
            port_scan_test("portal.local", AUTHORIZED, ports=range(1, 18), max_ports=16)


class TestParameterTamperingTest:
    def test_requires_authorization(self) -> None:
        with pytest.raises(Exception, match="parameter_tampering_test"):
            parameter_tampering_test(
                "https://portal.local/login?dst=https%3A%2F%2Fexample.com",
                AcquisitionPolicy(),
            )

    def test_safe_navigation_mutation_is_possible_bypass_evidence(self) -> None:
        calls: list[str] = []

        def request(url: str) -> ProbeResponse:
            calls.append(url)
            if "portallens-bypass-check" in unquote(url):
                return ProbeResponse(302, "https://example.com/landing")
            return ProbeResponse(302, "https://portal.local/login")

        evidence = parameter_tampering_test(
            "https://portal.local/login?dst=https%3A%2F%2Fexample.com",
            AUTHORIZED,
            request=request,
        )
        assert len(calls) == 2  # baseline + one mutation
        assert evidence[0].type is EvidenceType.BYPASS_PARAMETER
        assert evidence[0].key == "parameter_tampering:possible"
        assert "portallens-bypass-check" not in evidence[0].value

    def test_default_sentinel_redirect_is_detected(self) -> None:
        def request(url: str) -> ProbeResponse:
            if "portallens-bypass-check" in unquote(url):
                return ProbeResponse(302, "https://example.com/landing")
            return ProbeResponse(302, "https://portal.local/login")

        evidence = parameter_tampering_test(
            "https://portal.local/login?dst=https%3A%2F%2Foriginal.example",
            AUTHORIZED,
            request=request,
        )
        assert evidence[0].key == "parameter_tampering:possible"

    def test_sensitive_parameter_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="sensitive"):
            parameter_tampering_test(
                "https://portal.local/login?token=secret",
                AUTHORIZED,
                parameters=["token"],
                request=lambda url: ProbeResponse(200, url),
            )

    def test_no_safe_parameter_is_inconclusive_without_request(self) -> None:
        evidence = parameter_tampering_test("https://portal.local/login?foo=bar", AUTHORIZED)
        assert evidence[0].key == "parameter_tampering:inconclusive"


class TestBypassDetection:
    def setup_method(self) -> None:
        reset_evidence_ids()

    def test_report_detector_creates_findings_for_positive_evidence(self) -> None:
        report = PortalReport(
            portal_type="captive_wifi",
            primary_url="https://portal.local/login",
            evidence=[
                connect_test(
                    "proxy.local:8080",
                    "https://example.com",
                    AUTHORIZED,
                    connect_request=lambda proxy, target, timeout: ConnectResult(200),
                )[0],
                port_scan_test(
                    "portal.local", AUTHORIZED, ports=[443], probe_port=lambda host, port: True
                )[0],
            ],
        )
        findings = detect_bypass(report)
        assert {finding.check_slug for finding in findings} == {
            "bypass_connect_tunnel",
            "bypass_reachable_port",
        }
        assert all(finding.evidence_ids for finding in findings)

    def test_detector_maps_all_positive_probe_types(self) -> None:
        evidence = [
            Evidence(type=EvidenceType.BYPASS_CONNECT, source="connect://proxy/443", key="connect:allowed", value="allowed"),
            Evidence(type=EvidenceType.BYPASS_DNS, source="dns://probe.example", key="dns_tunnel:allowed", value="resolved"),
            Evidence(type=EvidenceType.BYPASS_CLICK_THROUGH, source="click-through://example.com", key="click_through:allowed", value="reached target"),
            Evidence(type=EvidenceType.BYPASS_PORT, source="port-scan://portal.local:443", key="port_scan:open", value="open"),
            Evidence(type=EvidenceType.BYPASS_PARAMETER, source="parameter-tamper://portal.local/dst", key="parameter_tampering:possible", value="possible bypass"),
        ]
        report = PortalReport(
            portal_type="captive_wifi",
            primary_url="https://portal.local/login",
            evidence=evidence,
        )
        assert {finding.check_slug for finding in detect_bypass(report)} == {
            "bypass_connect_tunnel",
            "bypass_dns_resolution",
            "bypass_click_through",
            "bypass_reachable_port",
            "bypass_parameter_tampering",
        }

    def test_negative_evidence_does_not_create_findings(self) -> None:
        report = PortalReport(
            portal_type="captive_wifi",
            primary_url="https://portal.local/login",
            evidence=connect_test(
                "proxy.local:8080",
                "https://example.com",
                AUTHORIZED,
                connect_request=lambda proxy, target, timeout: ConnectResult(403),
            ),
        )
        assert detect_bypass(report) == []

    def test_merge_preserves_report_and_adds_findings(self) -> None:
        report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        evidence = port_scan_test(
            "portal.local", AUTHORIZED, ports=[443], probe_port=lambda host, port: True
        )
        enriched = merge_bypass_evidence(report, evidence)
        assert report.evidence[-1].type is not EvidenceType.BYPASS_PORT
        assert enriched.evidence[-1].type is EvidenceType.BYPASS_PORT
        assert enriched.findings_for_check("bypass_reachable_port")
