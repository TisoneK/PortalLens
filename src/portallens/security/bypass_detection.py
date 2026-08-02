"""Report-level detection for captive-portal bypass potential.

The probes in :mod:`portallens.security.bypass` only collect observations.
This module turns positive observations into lightweight
:class:`SecurityFinding` records attached to a report by callers. A positive
finding means "a bounded test observed a condition consistent with bypass";
it is not proof that arbitrary traffic or authentication can be bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from portallens.evidence import Evidence, EvidenceType
from portallens.portal import PortalReport, SecurityFinding, Severity


@dataclass(frozen=True)
class _BypassRule:
    evidence_type: EvidenceType
    positive_keys: frozenset[str]
    check_slug: str
    title: str
    severity: Severity
    confidence: int
    note: str


_RULES: tuple[_BypassRule, ...] = (
    _BypassRule(
        evidence_type=EvidenceType.BYPASS_CONNECT,
        positive_keys=frozenset({"connect:allowed"}),
        check_slug="bypass_connect_tunnel",
        title="Captive portal may permit an HTTP CONNECT tunnel",
        severity=Severity.MEDIUM,
        confidence=78,
        note="A successful CONNECT response indicates possible tunnel bypass; application access was not verified.",
    ),
    _BypassRule(
        evidence_type=EvidenceType.BYPASS_DNS,
        positive_keys=frozenset({"dns_tunnel:allowed"}),
        check_slug="bypass_dns_resolution",
        title="DNS resolution may bypass captive-portal DNS controls",
        severity=Severity.MEDIUM,
        confidence=72,
        note="A normal answer was observed for the controlled DNS test; this does not prove arbitrary DNS or traffic bypass.",
    ),
    _BypassRule(
        evidence_type=EvidenceType.BYPASS_CLICK_THROUGH,
        positive_keys=frozenset({"click_through:allowed"}),
        check_slug="bypass_click_through",
        title="A request may reach the intended site before portal authentication",
        severity=Severity.HIGH,
        confidence=84,
        note="The request reached its intended host without submitting credentials; repeat with a controlled destination before treating this as confirmed bypass.",
    ),
    _BypassRule(
        evidence_type=EvidenceType.BYPASS_PORT,
        positive_keys=frozenset({"port_scan:open"}),
        check_slug="bypass_reachable_port",
        title="A service port is reachable before portal authentication (bypass not established)",
        severity=Severity.INFO,
        confidence=25,
        note="Port reachability is only a prerequisite signal; protocol-level access and click-through testing are still required.",
    ),
    _BypassRule(
        evidence_type=EvidenceType.BYPASS_PARAMETER,
        positive_keys=frozenset({"parameter_tampering:possible"}),
        check_slug="bypass_parameter_tampering",
        title="A navigation-parameter mutation may permit portal bypass",
        severity=Severity.HIGH,
        confidence=82,
        note="A benign navigation mutation reached a non-portal host; no exploit payload or credential was submitted.",
    ),
)


def detect_bypass(report: PortalReport) -> list[SecurityFinding]:
    """Analyze ``report`` evidence and return bypass-potential findings.

    Findings are grouped by technique, cite every positive evidence record,
    and are sorted by descending confidence. Existing report findings are not
    modified, so callers can safely use this function with any
    :class:`PortalReport` and merge or render the returned records as needed.
    """

    findings: list[SecurityFinding] = []
    for rule in _RULES:
        matches = [
            evidence
            for evidence in report.evidence
            if evidence.type is rule.evidence_type and evidence.key in rule.positive_keys
        ]
        if not matches:
            continue
        findings.append(
            SecurityFinding(
                check_slug=rule.check_slug,
                title=rule.title,
                severity=rule.severity,
                confidence=rule.confidence,
                affected=_affected_asset(report, matches),
                evidence_ids=[evidence.id for evidence in matches],
                impact=(
                    "The captive-portal enforcement boundary may not reliably prevent "
                    "pre-auth network access. This is potential bypass evidence, not a "
                    "demonstration of unrestricted internet access."
                ),
                remediation=(
                    "Reproduce the result with a controlled destination, then enforce "
                    "portal policy at the gateway for the affected protocol or parameter."
                ),
                verification_status="observed by a bounded authorized detection probe; independent verification recommended",
                note=rule.note,
            )
        )
    findings.sort(key=lambda finding: -finding.confidence)
    return findings


def merge_bypass_evidence(report: PortalReport, evidence: list[Evidence]) -> PortalReport:
    """Return ``report`` with bypass evidence and derived findings merged.

    This helper is intentionally immutable at the report boundary. It is
    useful after a caller runs one or more probes: evidence remains the source
    of truth, and the returned report carries both the existing findings and
    the new bypass findings without mutating the original report.
    """

    if not evidence:
        return report
    enriched = report.model_copy(update={"evidence": [*report.evidence, *evidence]})
    existing_slugs = {finding.check_slug for finding in enriched.findings}
    new_findings = [
        finding
        for finding in detect_bypass(enriched)
        if finding.check_slug not in existing_slugs
    ]
    return enriched.model_copy(update={"findings": [*enriched.findings, *new_findings]})


def _affected_asset(report: PortalReport, matches: list[Evidence]) -> str | None:
    """Prefer the target host in probe evidence, falling back to the report URL."""

    for evidence in matches:
        parsed = urlparse(evidence.source)
        if parsed.hostname:
            return parsed.hostname
    return urlparse(report.primary_url).hostname


__all__ = ["detect_bypass", "merge_bypass_evidence"]
