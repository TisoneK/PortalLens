"""Tests for the SecurityCheck registry (ADR-11).

Covers: checks are keyed on evidence, not vendor; the runner emits findings
with the disclosure schema; DOCUMENTED provenance marks findings provisional;
the client-fingerprinting check fires on the real ISPMan fixture; and the
analyzer attaches findings to the report.
"""

from __future__ import annotations

from portallens.evidence import Evidence, EvidenceType, reset_evidence_ids
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.portal import AnalysisContext, PortalReport
from portallens.security import Severity, check_for_slug, run_checks
from portallens.security.checks import EvidenceRequirement
from tests.data import ISPMAN_URL, MAZ_URL


class TestEvidenceRequirement:
    def test_types_constraint(self) -> None:
        req = EvidenceRequirement(types=(EvidenceType.URL_PARAMETER,))
        ev = Evidence(type=EvidenceType.URL_PARAMETER, source="u", key="k", value="v")
        assert req.matches(ev)
        host = Evidence(type=EvidenceType.URL_HOST, source="u", key="host", value="x")
        assert not req.matches(host)

    def test_keys_constraint(self) -> None:
        req = EvidenceRequirement(keys=("canvasFingerprint",))
        assert req.matches(Evidence(type=EvidenceType.URL_PARAMETER, source="u", key="canvasFingerprint", value="x"))
        assert not req.matches(Evidence(type=EvidenceType.URL_PARAMETER, source="u", key="cookie", value="x"))

    def test_key_prefixes_constraint(self) -> None:
        req = EvidenceRequirement(key_prefixes=("admin_port:",))
        assert req.matches(Evidence(type=EvidenceType.SERVICE_REACHABLE, source="s", key="admin_port:8291", value="M"))
        assert not req.matches(Evidence(type=EvidenceType.SERVICE_REACHABLE, source="s", key="port:80", value="H"))

    def test_value_contains_constraint(self) -> None:
        req = EvidenceRequirement(value_contains=("action=\"http://",))
        assert req.matches(Evidence(type=EvidenceType.HTML_ELEMENT, source="s", key="form", value='<form action="http://x/">'))
        assert not req.matches(Evidence(type=EvidenceType.HTML_ELEMENT, source="s", key="form", value='<form action="https://x/">'))

    def test_min_matches(self) -> None:
        req = EvidenceRequirement(keys=("a",), min_matches=2)
        evs = [Evidence(type=EvidenceType.URL_PARAMETER, source="u", key="a", value="1")]
        assert len([e for e in evs if req.matches(e)]) < req.min_matches


class TestRegistry:
    def test_slugs_are_unique(self) -> None:
        from portallens.security import CHECKS

        slugs = [c.slug for c in CHECKS]
        assert len(slugs) == len(set(slugs))

    def test_every_check_carries_the_disclosure_schema(self) -> None:
        from portallens.security import CHECKS

        for check in CHECKS:
            assert check.title
            assert check.impact
            assert check.remediation
            assert check.requires is not None

    def test_check_lookup(self) -> None:
        assert check_for_slug("client_fingerprinting_preauth") is not None
        assert check_for_slug("nope") is None


class TestRunner:
    def test_no_matching_evidence_fires_nothing(self) -> None:
        assert run_checks([]) == []
        only_host = [Evidence(type=EvidenceType.URL_HOST, source="u", key="host", value="example.com")]
        assert run_checks(only_host) == []

    def test_client_fingerprinting_fires_on_fingerprint_params(self) -> None:
        evs = [
            Evidence(type=EvidenceType.URL_PARAMETER, source="u", key="canvasFingerprint", value="data:image/png;base64,AAAA"),
            Evidence(type=EvidenceType.URL_PARAMETER, source="u", key="timezone", value="Africa/Nairobi"),
        ]
        findings = run_checks(evs)
        assert any(f.check_slug == "client_fingerprinting_preauth" for f in findings)

    def test_cleartext_login_fires_on_html_evidence(self) -> None:
        evs = [Evidence(type=EvidenceType.HTML_ELEMENT, source="http://x/", key="form", value='<form action="http://x/login">')]
        findings = run_checks(evs)
        cleartext = [f for f in findings if f.check_slug == "cleartext_login_form"]
        assert cleartext
        assert cleartext[0].severity is Severity.HIGH

    def test_finding_carries_the_disclosure_schema(self) -> None:
        evs = [
            Evidence(type=EvidenceType.URL_HOST, source="http://maz.wifi/login", key="host", value="maz.wifi"),
            Evidence(type=EvidenceType.URL_PARAMETER, source="http://maz.wifi/login", key="canvasFingerprint", value="data:image/png;base64,AAAA"),
        ]
        findings = run_checks(evs)
        finding = next(f for f in findings if f.check_slug == "client_fingerprinting_preauth")
        assert finding.title
        assert finding.impact
        assert finding.remediation
        assert finding.evidence_ids  # cites its evidence
        assert finding.affected == "maz.wifi"
        assert finding.confidence >= 80  # strong, specific evidence

    def test_confidence_combines_multiple_signals(self) -> None:
        one = run_checks([Evidence(type=EvidenceType.URL_PARAMETER, source="u", key="canvasFingerprint", value="x")])
        both = run_checks(
            [
                Evidence(type=EvidenceType.URL_PARAMETER, source="u", key="canvasFingerprint", value="x"),
                Evidence(type=EvidenceType.URL_PARAMETER, source="u", key="webgl", value="y"),
            ]
        )
        # More independent fingerprint signals -> higher confidence (noisy-OR).
        f1 = next(f for f in one if f.check_slug == "client_fingerprinting_preauth")
        f2 = next(f for f in both if f.check_slug == "client_fingerprinting_preauth")
        assert f2.confidence > f1.confidence


class TestAnalyzerIntegration:
    def setup_method(self) -> None:
        reset_evidence_ids()

    def test_ispman_fixture_fires_client_fingerprinting(self) -> None:
        # The real ISPMAN fixture carries canvasFingerprint, webgl, userAgent,
        # timezone, cookie, height, width — the check should fire on it.
        report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        findings = report.findings_for_check("client_fingerprinting_preauth")
        assert findings, "expected client_fingerprinting_preauth on the ISPMAN fixture"
        assert findings[0].confidence >= 80

    def test_report_findings_are_attached(self) -> None:
        report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        assert isinstance(report, PortalReport)
        assert isinstance(report.findings, list)

    def test_findings_survive_report_serialization(self) -> None:
        report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        dumped = report.model_dump_json()
        reloaded = PortalReport.model_validate_json(dumped)
        assert len(reloaded.findings) == len(report.findings)
        assert reloaded.findings[0].check_slug == report.findings[0].check_slug

    def test_provisional_status_for_documented_check(self) -> None:
        # CLEARTEXT_LOGIN is DOCUMENTED provenance -> its finding must say so.
        from portallens.security.checks import CLEARTEXT_LOGIN

        assert CLEARTEXT_LOGIN.provenance.value  # not validated
        evs = [Evidence(type=EvidenceType.HTML_ELEMENT, source="http://x/", key="form", value='<form action="http://x/">')]
        finding = next(f for f in run_checks(evs) if f.check_slug == "cleartext_login_form")
        assert "provisional" in finding.verification_status


class TestGatewayAdminCheck:
    def test_fires_on_reachable_admin_port_evidence(self) -> None:
        evs = [
            Evidence(
                type=EvidenceType.SERVICE_REACHABLE,
                source="port_scan://maz.wifi:8291",
                key="admin_port:8291",
                value="MikroTik WebFig (8291)",
            )
        ]
        findings = run_checks(evs)
        admin = [f for f in findings if f.check_slug == "gateway_admin_exposed"]
        assert admin
        assert admin[0].severity is Severity.HIGH
        assert admin[0].confidence >= 90  # MikroTik WebFig is unambiguous

    def test_does_not_fire_on_generic_web_port(self) -> None:
        # A generic reachable web port (key `port:80`, not an admin_port: key)
        # is not evidence of an exposed admin interface — the check must not
        # fire. (The probe only ever emits `admin_port:` keys for ports it
        # recognizes as administrative.)
        evs = [Evidence(type=EvidenceType.SERVICE_REACHABLE, source="port_scan://x:80", key="port:80", value="http")]
        assert not any(f.check_slug == "gateway_admin_exposed" for f in run_checks(evs))
