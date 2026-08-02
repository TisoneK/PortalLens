"""Security — the security-findings surface (ADR-11/12/13).

- :mod:`portallens.security.checks` — the SecurityCheck registry: security
  checks as data, keyed on the evidence they require, never on the vendor.
- :mod:`portallens.security.audit` — NetAudit: authorized active assessment
  (admin-port probing) gated behind the single ``AcquisitionPolicy.authorized``
  flag (ADR-15).

- :mod:`portallens.security.bypass` — bounded authorized probes for
  CONNECT, DNS, click-through, port reachability, and parameter tampering.
- :mod:`portallens.security.bypass_detection` — report-level findings from
  positive bypass evidence; it never performs the probes itself.

Findings may be lightweight (ADR-17): check, title, severity, and confidence
are required; Impact, Affected asset, Evidence, Remediation, and Verification
status are included when present.
"""

from __future__ import annotations

from portallens.security.bypass import (
    DEFAULT_BYPASS_PORTS,
    ConnectResult,
    ProbeResponse,
    click_through_test,
    connect_test,
    dns_tunnel_test,
    parameter_tampering_test,
    port_scan_test,
)
from portallens.security.bypass_detection import detect_bypass, merge_bypass_evidence
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
    "DEFAULT_BYPASS_PORTS",
    "ConnectResult",
    "EvidenceRequirement",
    "ProbeResponse",
    "SecurityCheck",
    "SecurityFinding",
    "Severity",
    "check_for_slug",
    "click_through_test",
    "connect_test",
    "detect_bypass",
    "dns_tunnel_test",
    "merge_bypass_evidence",
    "parameter_tampering_test",
    "port_scan_test",
    "run_checks",
]
