"""Tests for the SARIF renderer (reporting/sarif.py).

SARIF 2.1.0 is the industry-standard interchange for security findings —
the shape here is what GitHub code scanning / Azure DevOps consume.
"""

from __future__ import annotations

import json

from portallens.evidence import reset_evidence_ids
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.portal import AnalysisContext
from portallens.reporting import render_sarif
from tests.data import ISPMAN_URL, MAZ_URL


def _report():
    reset_evidence_ids()
    return CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))


class TestSarifStructure:
    def test_is_valid_sarif_21(self) -> None:
        doc = json.loads(render_sarif(_report()))
        assert doc["version"] == "2.1.0"
        assert doc["$schema"].endswith("sarif-schema-2.1.0.json")
        assert len(doc["runs"]) == 1

    def test_runs_carry_tool_driver(self) -> None:
        run = json.loads(render_sarif(_report()))["runs"][0]
        assert run["tool"]["driver"]["name"] == "PortalLens"
        assert run["tool"]["driver"]["rules"]

    def test_findings_become_rules_and_results(self) -> None:
        report = _report()
        doc = json.loads(render_sarif(report))
        run = doc["runs"][0]
        rule_ids = {r["id"] for r in run["tool"]["driver"]["rules"]}
        result_rule_ids = {r["ruleId"] for r in run["results"]}
        assert result_rule_ids == {f.check_slug for f in report.findings}
        assert result_rule_ids <= rule_ids

    def test_result_carries_evidence_and_confidence(self) -> None:
        report = _report()
        doc = json.loads(render_sarif(report))
        result = doc["runs"][0]["results"][0]
        props = result["properties"]
        assert props["evidenceIds"]  # traceable to the report evidence table
        assert 0 <= props["confidence"] <= 100
        assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]

    def test_severity_maps_to_level(self) -> None:
        report = _report()
        doc = json.loads(render_sarif(report))
        for result in doc["runs"][0]["results"]:
            finding = next(f for f in report.findings if f.check_slug == result["ruleId"])
            if finding.severity.value in ("high", "critical"):
                assert result["level"] == "error"
            elif finding.severity.value == "medium":
                assert result["level"] == "warning"
            else:
                assert result["level"] == "note"

    def test_empty_report_renders_empty_results(self) -> None:
        from portallens.portal import PortalReport, PortalType

        report = PortalReport(portal_type=PortalType.CAPTIVE_WIFI, primary_url="http://example.com")
        doc = json.loads(render_sarif(report))
        assert doc["runs"][0]["results"] == []
        assert doc["runs"][0]["tool"]["driver"]["rules"] == []


class TestMarkdownFindingsSection:
    def test_markdown_includes_findings_section(self) -> None:
        from portallens.reporting import render_markdown

        markdown = render_markdown(_report())
        assert "## Security Findings" in markdown
        assert "client_fingerprinting_preauth" in markdown
        assert "Recommended remediation" in markdown
