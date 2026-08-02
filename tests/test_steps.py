"""Tests for the AnalysisStep registry (ADR-9) and its first steps.

Covers: registry invariants; the computed "next investigation" queue matches
open questions; the resolve_dns step is gated behind the single
``AcquisitionPolicy.authorized`` flag (ADR-15) and produces DNS_RECORD
evidence; the ip_asn_lookup step resolves hostnames + queries OSINT under the
same single flag and produces IP_ASN evidence; and
investigation.append_evidence appends to the report + audit log.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portallens.acquisition import AcquisitionDenied
from portallens.evidence import EvidenceType, reset_evidence_ids
from portallens.investigation import Investigation, InvestigationStore
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.portal import AcquisitionPolicy, AnalysisContext, PortalType, RelationshipKind
from portallens.steps import (
    compute_next_steps,
    hosts_from_report,
    registered_steps,
    step_for_slug,
)
from tests.data import ISPMAN_URL, MAZ_URL


def _investigation() -> Investigation:
    reset_evidence_ids()
    report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
    return Investigation.start(report, portal_type=PortalType.CAPTIVE_WIFI)


class TestRegistry:
    def test_steps_are_registered(self) -> None:
        slugs = {s.slug for s in registered_steps()}
        assert {"resolve_dns", "ip_asn_lookup"} <= slugs

    def test_step_for_slug(self) -> None:
        assert step_for_slug("resolve_dns") is not None
        assert step_for_slug("nope") is None

    def test_steps_declare_requires_and_produces(self) -> None:
        for step in registered_steps():
            assert step.label
            assert step.produces
            # resolve_dns/ip_asn_lookup are active; both must name a technique.
            assert step.requires is not None

    def test_registration_rejects_duplicates(self) -> None:
        from portallens.steps.registry import AnalysisStep, register_step

        dup = AnalysisStep(
            slug="resolve_dns",
            label="dup",
            requires="resolve_dns",
            produces=(EvidenceType.DNS_RECORD,),
            answers=(),
            run=lambda inv, policy: [],
        )
        with pytest.raises(ValueError, match="already registered"):
            register_step(dup)


class TestNextSteps:
    def test_compute_next_steps_matches_open_questions(self) -> None:
        inv = _investigation()
        steps = compute_next_steps(inv.report.open_questions)
        slugs = [s.slug for s in steps]
        # The upstream-ISP question names resolve_dns + ip_asn_lookup (ADR-9);
        # the admin-exposure question names port_scan (not a registered step yet,
        # so it's omitted from the runnable queue).
        assert "resolve_dns" in slugs
        assert "ip_asn_lookup" in slugs
        assert "port_scan" not in slugs

    def test_queue_is_deduplicated(self) -> None:
        steps = compute_next_steps([q for q in _investigation().report.open_questions])
        slugs = [s.slug for s in steps]
        assert len(slugs) == len(set(slugs))

    def test_hosts_from_report(self) -> None:
        inv = _investigation()
        hosts = hosts_from_report(inv.report)
        assert "maz.wifi" in hosts
        assert "captive.ispman.tech" in hosts


class TestResolveDnsStep:
    def test_requires_authorized_policy(self) -> None:
        inv = _investigation()
        step = step_for_slug("resolve_dns")
        assert step is not None
        with pytest.raises(AcquisitionDenied):
            step.run(inv, AcquisitionPolicy())  # passive policy forbids

    def test_produces_dns_record_evidence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from portallens.steps import dns as dns_mod

        monkeypatch.setattr(dns_mod, "resolve_host", lambda host: ["192.0.2.1", "2001:db8::1"])
        inv = _investigation()
        step = step_for_slug("resolve_dns")
        assert step is not None
        evidence = step.run(inv, AcquisitionPolicy(authorized=True))
        assert evidence
        assert all(ev.type is EvidenceType.DNS_RECORD for ev in evidence)
        assert all(ev.value for ev in evidence)  # resolved addresses


class TestIpAsnStep:
    def test_requires_authorized_policy(self) -> None:
        inv = _investigation()
        step = step_for_slug("ip_asn_lookup")
        assert step is not None
        # ADR-15: one flag unlocks every active technique — a passive policy
        # forbids the OSINT lookup regardless of technique.
        with pytest.raises(AcquisitionDenied):
            step.run(inv, AcquisitionPolicy())

    def test_resolves_hostnames_and_queries_osint_under_the_single_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ADR-15 replaced ADR-13's tiers: with the single authorized flag set,
        # the step resolves the target's hostnames (DNS) and looks them up
        # (OSINT) — no separate DNS consent is needed.
        from portallens.steps import dns as dns_mod
        from portallens.steps import ip_asn as ip_asn_mod

        called: list[str] = []

        def tracking_resolve(host: str) -> list[str]:
            called.append(host)
            return ["192.0.2.1"]

        monkeypatch.setattr(dns_mod, "resolve_host", tracking_resolve)
        monkeypatch.setattr(ip_asn_mod, "whois_for_ip", lambda ip: [("asn", "AS64500")])
        inv = _investigation()
        step = step_for_slug("ip_asn_lookup")
        assert step is not None

        evidence = step.run(inv, AcquisitionPolicy(authorized=True))
        assert called, "hostnames must be resolved then looked up under the single flag"
        assert evidence
        assert all(ev.type is EvidenceType.IP_ASN for ev in evidence)

    def test_produces_ip_asn_evidence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from portallens.steps import dns as dns_mod
        from portallens.steps import ip_asn as ip_asn_mod

        monkeypatch.setattr(dns_mod, "resolve_host", lambda host: ["192.0.2.1"])
        monkeypatch.setattr(ip_asn_mod, "whois_for_ip", lambda ip: [("asn", "AS64500"), ("org-name", "Test Org")])
        inv = _investigation()
        step = step_for_slug("ip_asn_lookup")
        assert step is not None
        evidence = step.run(inv, AcquisitionPolicy(authorized=True))
        assert evidence
        assert all(ev.type is EvidenceType.IP_ASN for ev in evidence)


class TestRefineOpenQuestions:
    """ADR-9 loop closure — questions close once the evidence answers them."""

    def test_upstream_question_closes_when_ip_asn_evidence_lands(self) -> None:
        from portallens.evidence import Evidence
        from portallens.steps import refine_open_questions

        inv = _investigation()
        questions = inv.report.open_questions
        upstream = next(q for q in questions if q.kind is RelationshipKind.UPSTREAM_OF)
        assert upstream in questions

        # DNS records alone don't close "who is upstream" — the question names
        # resolve_dns + ip_asn_lookup, and only ip_asn_lookup's IP_ASN evidence
        # answers it (ADR-9: closure is evidence-driven).
        dns_only = refine_open_questions(
            questions,
            [Evidence(type=EvidenceType.DNS_RECORD, source="dns://x", key="a", value="192.0.2.1")],
        )
        assert upstream in dns_only

        answered = refine_open_questions(
            questions,
            [Evidence(type=EvidenceType.IP_ASN, source="ripe://x", key="asn", value="AS64500")],
        )
        assert upstream not in answered

    def test_admin_question_closes_when_probe_evidence_lands(self) -> None:
        from portallens.evidence import Evidence
        from portallens.steps import refine_open_questions

        inv = _investigation()
        questions = inv.report.open_questions
        admin = next(q for q in questions if "administrative interface" in q.question)
        assert admin in questions

        # SERVICE_REACHABLE (NetAudit) answers the admin-exposure question —
        # the probe-driven closure, not a step's evidence types.
        answered = refine_open_questions(
            questions,
            [Evidence(type=EvidenceType.SERVICE_REACHABLE, source="port_scan://x:8291", key="admin_port:8291", value="M")],
        )
        assert admin not in answered

    def test_unanswerable_questions_stay_open(self) -> None:
        # Documented-signature questions (Provenance.DOCUMENTED — no capture
        # validates them) have no registered step that can answer them, so
        # nothing closes them. The fixture's ISPMan/MikroTik signatures are
        # VALIDATED and don't emit one, so construct the question directly.
        from portallens.evidence import Evidence
        from portallens.portal import OpenQuestion
        from portallens.steps import refine_open_questions

        documented = OpenQuestion(
            subject="CoovaChilli",
            question=(
                "Does the CoovaChilli fingerprint hold in the field? Its "
                "signature was transcribed from vendor documentation and has "
                "not been validated against a captured URL — treat the match "
                "as provisional."
            ),
        )
        refined = refine_open_questions(
            [documented], [Evidence(type=EvidenceType.IP_ASN, source="s", key="asn", value="AS1")]
        )
        assert documented in refined


class TestAppendEvidence:
    def test_appends_to_report_and_audit(self) -> None:
        from portallens.evidence import Evidence

        inv = _investigation()
        before = len(inv.report.evidence)
        audit_before = len(inv.audit_log)
        inv.append_evidence(
            [Evidence(type=EvidenceType.DNS_RECORD, source="dns://maz.wifi", key="a", value="192.0.2.1")],
            step="resolve_dns",
        )
        assert len(inv.report.evidence) == before + 1
        assert len(inv.audit_log) == audit_before + 1
        assert inv.audit_log[-1].kind == "step"
        assert "resolve_dns" in inv.audit_log[-1].detail

    def test_empty_evidence_is_a_no_op(self) -> None:
        inv = _investigation()
        before = len(inv.report.evidence)
        inv.append_evidence([], step="resolve_dns")
        assert len(inv.report.evidence) == before

    def test_survives_store_round_trip(self, tmp_path: Path) -> None:
        from portallens.evidence import Evidence

        inv = _investigation()
        inv.append_evidence(
            [Evidence(type=EvidenceType.DNS_RECORD, source="dns://maz.wifi", key="a", value="192.0.2.1")],
            step="resolve_dns",
        )
        with InvestigationStore(tmp_path / "db.sqlite") as store:
            store.save(inv)
            loaded = store.get(inv.id)
        assert loaded is not None
        assert len(loaded.report.evidence) == len(inv.report.evidence)
        assert loaded.audit_log[-1].kind == "step"
