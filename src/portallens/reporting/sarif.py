"""SARIF output — industry-standard interchange for security findings.

SARIF 2.1.0 (Static Analysis Results Interchange Format) is what GitHub
code scanning, Azure DevOps, and other security tooling consume. The
rendering here maps each :class:`~portallens.portal.SecurityFinding` onto a
SARIF rule + result:

- finding title → rule ``shortDescription``
- severity → SARIF ``level`` (critical/high → ``error``, medium → ``warning``,
  low/info → ``note``)
- evidence ids → result ``properties`` (so a reader can trace the finding
  back to the report's evidence table)
- affected asset → result location URI

SARIF is only meaningful once a report carries findings — passive analysis
without findings renders an empty ``results`` list (valid SARIF, nothing to
report).
"""

from __future__ import annotations

import json
from typing import Any

from portallens.confidence import _label_for
from portallens.portal import PortalReport, SecurityFinding, Severity

_SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/"
    "Schemata/sarif-schema-2.1.0.json"
)

_LEVEL_BY_SEVERITY: dict[Severity, str] = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}


def _rule_for(finding: SecurityFinding) -> dict[str, Any]:
    """One SARIF reportingDescriptor per check slug."""

    properties: dict[str, Any] = {
        "severity": finding.severity.value,
        "confidence": finding.confidence,
        "confidenceLabel": _label_for(finding.confidence).value,
    }
    if finding.verification_status:
        properties["verificationStatus"] = finding.verification_status
    return {
        "id": finding.check_slug,
        "name": finding.check_slug,
        "shortDescription": {"text": finding.title},
        "properties": properties,
    }


def _result_for(finding: SecurityFinding, report: PortalReport) -> dict[str, Any]:
    """One SARIF result per finding."""

    # ADR-17: prose fields are optional — only set what the finding carries.
    affected = finding.affected or report.primary_url
    markdown = f"**{finding.title}**"
    if finding.impact:
        markdown += f" — {finding.impact}"
    properties: dict[str, Any] = {
        "evidenceIds": finding.evidence_ids,
        "confidence": finding.confidence,
        "affectedAsset": affected,
    }
    if finding.remediation:
        properties["remediation"] = finding.remediation
    if finding.verification_status:
        properties["verificationStatus"] = finding.verification_status
    return {
        "ruleId": finding.check_slug,
        "level": _LEVEL_BY_SEVERITY.get(finding.severity, "note"),
        "message": {
            "text": finding.title,
            "markdown": markdown,
        },
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": affected},
                }
            }
        ],
        "properties": properties,
    }


def render_sarif(report: PortalReport) -> str:
    """Render ``report``'s findings as a SARIF 2.1.0 document (JSON string)."""

    rules = list({f.check_slug: _rule_for(f) for f in report.findings}.values())
    results = [_result_for(f, report) for f in report.findings]

    document = {
        "$schema": _SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "PortalLens",
                        "informationUri": "https://github.com/TisoneK/PortalLens",
                        "rules": rules,
                    }
                },
                "results": results,
                "properties": {"primaryUrl": report.primary_url},
            }
        ],
    }
    return json.dumps(document, indent=2)
