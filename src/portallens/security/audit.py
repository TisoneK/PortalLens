"""NetAudit — authorized active security assessment (backlogged, ADR-12).

NetAudit runs **only** when the caller sets the single
``AcquisitionPolicy.authorized`` flag (ADR-15) AND has authorization for
the target. It probes for evidence the passive analyzer cannot reach — a
reachable admin port, an exposed admin path — records it as
:class:`Evidence` records, and re-runs the SecurityCheck registry over the
enriched evidence so the ``gateway_admin_exposed`` check can fire on the
probe results.

The probe function takes an injectable ``probe_port`` callable so tests can
exercise the logic without touching the network; the default uses ``socket``.

The probes only *detect* that a service is reachable — no exploit action
(authenticating, submitting credentials, bypassing) is implemented (ADR-16
lifted the assess-only ban at the records level, but nothing beyond
detection has been built).
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from dataclasses import dataclass, field

from portallens.acquisition import assert_policy
from portallens.evidence import Evidence, EvidenceType
from portallens.portal import AcquisitionPolicy, SecurityFinding
from portallens.security.checks import run_checks

#: Well-known administrative ports for the gateways the captive_wifi plugin
#: recognizes. The value is the service label that lands in evidence.
ADMIN_PORTS: dict[int, str] = {
    8291: "MikroTik WebFig (8291)",
    8728: "MikroTik API (8728)",
    8729: "MikroTik API TLS (8729)",
    22: "SSH (22)",
    23: "Telnet (23)",
}


@dataclass(frozen=True)
class AuditResult:
    """The outcome of an authorized active-assessment pass."""

    evidence: list[Evidence] = field(default_factory=list)
    findings: list[SecurityFinding] = field(default_factory=list)


def probe_admin_ports(
    hosts: list[str],
    policy: AcquisitionPolicy,
    *,
    probe_port: Callable[[str, int], bool] | None = None,
    connect_timeout: float = 2.0,
) -> list[Evidence]:
    """Probe the well-known admin ports on ``hosts``.

    Gated behind the single ``AcquisitionPolicy.authorized`` flag (ADR-15)
    — raises :class:`AcquisitionDenied` if it is not set. Returns one
    ``SERVICE_REACHABLE`` evidence record per (host, port) that accepted a
    connection. The evidence key ``admin_port:<port>`` is what the
    ``gateway_admin_exposed`` check keys on.
    """

    assert_policy(policy, "port_scan")
    connect = probe_port or (lambda host, port: _socket_connect(host, port, timeout=connect_timeout))
    evidence: list[Evidence] = []
    for host in hosts:
        for port, service in ADMIN_PORTS.items():
            try:
                if connect(host, port):
                    evidence.append(
                        Evidence(
                            type=EvidenceType.SERVICE_REACHABLE,
                            source=f"port_scan://{host}:{port}",
                            key=f"admin_port:{port}",
                            value=service,
                            note=(
                                f"Port {port} on {host} accepted a connection during "
                                "an authorized admin-port probe."
                            ),
                        )
                    )
            except OSError:
                # The connection was refused / unreachable — that's the
                # negative result we're probing for; not an error.
                continue
    return evidence


def run_netaudit(
    hosts: list[str],
    policy: AcquisitionPolicy,
    *,
    probe_port: Callable[[str, int], bool] | None = None,
) -> AuditResult:
    """Run the authorized active-assessment pass over ``hosts``.

    Currently one technique is implemented — admin-port probing
    (``port_scan``). The pass always re-runs the SecurityCheck registry over
    the probe evidence so findings fire on what the probe actually saw.
    """

    evidence: list[Evidence] = []
    if policy.authorized:
        evidence.extend(probe_admin_ports(hosts, policy, probe_port=probe_port))
    findings = run_checks(evidence)
    return AuditResult(evidence=evidence, findings=findings)


def _socket_connect(host: str, port: int, timeout: float) -> bool:
    """Connect to ``host:port`` and return True if the connection succeeds.

    ``timeout`` is accepted positionally to match the injected callable
    signature; callers using the default never hit a long block.
    """

    with socket.create_connection((host, port), timeout=timeout):
        return True
