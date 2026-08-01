"""DNS resolution step (ADR-9) — the lowest-risk active technique.

Resolves a hostname to A/AAAA records via the stdlib ``socket`` module and
records each address as :class:`~portallens.evidence.EvidenceType.DNS_RECORD`
evidence. Gated behind ``AcquisitionPolicy.resolve_dns``; per ADR-10 the
step also checks the investigation's recorded authorization.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from portallens.acquisition import assert_policy
from portallens.evidence import Evidence, EvidenceType
from portallens.portal import AcquisitionPolicy
from portallens.steps.registry import AnalysisStep, register_step

if TYPE_CHECKING:
    from portallens.investigation.models import Investigation

#: The resolver callable is injectable so tests never touch the network.
Resolver = Callable[[str, None], list[tuple[Any, ...]]]


def resolve_host(host: str, *, resolver: Resolver | None = None) -> list[str]:
    """Resolve ``host`` to a list of A/AAAA addresses (deduplicated)."""

    try:
        infos = resolver(host, None) if resolver is not None else socket.getaddrinfo(host, None)
    except OSError:
        return []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            seen.add(sockaddr[0])
    return sorted(seen)


def run_resolve_dns(investigation: Investigation, policy: AcquisitionPolicy) -> list[Evidence]:
    """Resolve every hostname in the investigation's report to A/AAAA."""

    from portallens.steps.registry import hosts_from_report

    assert_policy(policy, "resolve_dns")
    evidence: list[Evidence] = []
    for host in hosts_from_report(investigation.report):
        for addr in resolve_host(host):
            evidence.append(
                Evidence(
                    type=EvidenceType.DNS_RECORD,
                    source=f"resolve_dns://{host}",
                    key="a",
                    value=addr,
                    note=f"DNS A/AAAA record for {host}",
                )
            )
    return evidence


register_step(
    AnalysisStep(
        slug="resolve_dns",
        label="Resolve DNS records (A/AAAA) for observed hosts",
        requires="resolve_dns",
        produces=(EvidenceType.DNS_RECORD,),
        answers=(),
        run=run_resolve_dns,
    )
)
