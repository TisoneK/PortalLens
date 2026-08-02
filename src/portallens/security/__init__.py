"""Security — the security-findings surface (ADR-11/12/13).

- :mod:`portallens.security.checks` — the SecurityCheck registry: security
  checks as data, keyed on the evidence they require, never on the vendor.
- :mod:`portallens.security.audit` — NetAudit: authorized active assessment
  (admin-port probing) gated behind the single ``AcquisitionPolicy.authorized``
  flag (ADR-15).

Findings may be lightweight (ADR-17): check, title, severity, and confidence
are required; Impact, Affected asset, Evidence, Remediation, and Verification
status are included when present.
"""

from __future__ import annotations

from portallens.security.checks import (
    CHECKS,
    EvidenceRequirement,
    SecurityCheck,
    check_for_slug,
    run_checks,
)
from portallens.security.findings import SecurityFinding, Severity

__all__ = [
    "CHECKS",
    "EvidenceRequirement",
    "SecurityCheck",
    "SecurityFinding",
    "Severity",
    "check_for_slug",
    "run_checks",
]
