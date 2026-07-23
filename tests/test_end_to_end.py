"""End-to-end tests — run the analyzer on the real ISPMan URL pair and
verify the report contains the expected sections."""

from __future__ import annotations

from portallens.evidence import reset_evidence_ids
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.portal import AnalysisContext, PortalType, RelationshipKind
from portallens.registry import get_portal_class
from portallens.reporting import render_markdown
from tests.data import ISPMAN_URL, MAZ_URL


class TestEndToEnd:
    def setup_method(self) -> None:
        reset_evidence_ids()

    def test_analyzer_runs_on_ispman_url(self) -> None:
        portal = CaptiveWifiPortal()
        report = portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        assert report.portal_type is PortalType.CAPTIVE_WIFI
        assert report.primary_url == ISPMAN_URL

    def test_report_contains_both_fingerprints(self) -> None:
        portal = CaptiveWifiPortal()
        report = portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        platforms = {fp.platform for fp in report.fingerprints}
        assert "ISPMan" in platforms
        assert "MikroTik RouterOS Hotspot" in platforms

    def test_report_contains_relationships(self) -> None:
        portal = CaptiveWifiPortal()
        report = portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        assert len(report.relationships) >= 3
        kinds = {r.kind for r in report.relationships}
        assert RelationshipKind.REDIRECTS_TO in kinds
        assert RelationshipKind.USES_PLATFORM in kinds
        assert RelationshipKind.OPERATES_NETWORK in kinds

    def test_report_distinguishes_facts_inferences_hypotheses(self) -> None:
        portal = CaptiveWifiPortal()
        report = portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        facts = report.observations_of_kind("fact")
        inferences = report.observations_of_kind("inference")
        hypotheses = report.observations_of_kind("hypothesis")
        assert facts, "expected at least one observed fact"
        assert inferences, "expected at least one inference"
        assert hypotheses, "expected at least one hypothesis (RESELLS_BANDWIDTH is explicitly low-confidence)"

    def test_hypotheses_never_exceed_low_confidence(self) -> None:
        portal = CaptiveWifiPortal()
        report = portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        for h in report.observations_of_kind("hypothesis"):
            assert h.confidence <= 39, (
                f"hypothesis '{h.statement}' has confidence {h.confidence}, "
                "should be capped at 39 (low) by convention"
            )

    def test_report_contains_open_questions(self) -> None:
        portal = CaptiveWifiPortal()
        report = portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        assert report.open_questions
        # The upstream-ISP question is mandatory — it's always open
        # without authorized active assessment.
        assert any("upstream" in q.question.lower() for q in report.open_questions)

    def test_upstream_question_is_a_structured_unknown_edge(self) -> None:
        # The upstream-ISP question maps to an UPSTREAM_OF edge and names the
        # steps that could resolve it (ADR-9) — this is what lets a graph view
        # draw it as an explicit unknown edge and a "next investigation" queue
        # be computed.
        portal = CaptiveWifiPortal()
        report = portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        upstream = next(q for q in report.open_questions if "upstream" in q.question.lower())
        assert upstream.kind is RelationshipKind.UPSTREAM_OF
        assert upstream.subject  # names the entity the gap is about
        assert "ip_asn_lookup" in upstream.resolves_with

    def test_gateway_admin_question_names_resolving_steps(self) -> None:
        # The MikroTik gateway fires on the fixture, so there's an admin-exposure
        # question — and it names the active steps that would answer it.
        portal = CaptiveWifiPortal()
        report = portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        admin = [q for q in report.open_questions if "administrative interface" in q.question]
        assert admin
        assert all("port_scan" in q.resolves_with for q in admin)

    def test_markdown_render_includes_all_sections(self) -> None:
        portal = CaptiveWifiPortal()
        report = portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        markdown = render_markdown(report)
        assert "# PortalLens Report — Captive Wi-Fi Portal" in markdown
        assert "## Executive Summary" in markdown
        assert "## Captured Evidence" in markdown
        assert "## Observed Facts" in markdown
        assert "## Inferences" in markdown
        assert "## Hypotheses" in markdown
        assert "## Platform Fingerprints" in markdown
        assert "## Inferred Relationships" in markdown
        assert "## Open Questions" in markdown
        assert "## Confidence Rubric" in markdown

    def test_markdown_render_mentions_ispman_and_maz(self) -> None:
        portal = CaptiveWifiPortal()
        report = portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        markdown = render_markdown(report)
        assert "ISPMan" in markdown
        assert "maz.wifi" in markdown

    def test_registry_returns_captive_wifi_portal(self) -> None:
        cls = get_portal_class(PortalType.CAPTIVE_WIFI)
        assert cls is CaptiveWifiPortal
