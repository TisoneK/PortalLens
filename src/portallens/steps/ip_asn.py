"""IP/ASN lookup step (ADR-9, ADR-13 Tier-1 OSINT) — closes "who is upstream?"

Queries RIPEstat (a third-party OSINT API) for the ASN and holder of an IP
and records them as :class:`~portallens.evidence.EvidenceType.IP_ASN`
evidence. Gated behind ``AcquisitionPolicy.use_osint_apis`` (ADR-13): it
leaves the machine but never touches the target — it is neither passive nor
target-facing-active, it is its own middle tier.

The DNS fallback (resolving a hostname to an IP so it can be looked up) is
**not** implied by OSINT consent (ADR-13: enabling one tier never implies
another). It only runs when the policy also enables ``resolve_dns`` —
otherwise hostnames are skipped and only IP literals are looked up.

The HTTP client is injectable so tests exercise the parsing without the
network. The default uses ``httpx`` (already a dependency).
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING, Any

import httpx

from portallens.acquisition import assert_policy
from portallens.evidence import Evidence, EvidenceType
from portallens.portal import AcquisitionPolicy, RelationshipKind
from portallens.steps.registry import AnalysisStep, register_step

if TYPE_CHECKING:
    from portallens.investigation.models import Investigation

_RIPE_WHOIS_URL = "https://stat.ripe.net/data/whois/data.json?resource={ip}"


def is_ip(host: str) -> bool:
    """True if ``host`` is already an IP literal (so we skip DNS)."""

    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def whois_for_ip(ip: str, *, client: Any | None = None) -> list[tuple[str, str]]:
    """Query RIPEstat whois for ``ip``; return ``(key, value)`` pairs.

    Returns the ``org-name`` / ``asn`` / ``netname`` fields found in the
    first record block, in that priority order — the fields that tell you
    who owns the address and which ASN it belongs to.
    """

    http = client or httpx.Client(timeout=10.0)
    url = _RIPE_WHOIS_URL.format(ip=ip)
    try:
        response = http.get(url)
    finally:
        if client is None:
            http.close()
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", {})
    records = data.get("records", [])
    out: list[tuple[str, str]] = []
    for block in records:
        fields = {entry.get("key"): entry.get("value") for entry in block if isinstance(entry, dict)}
        for key in ("asn", "org-name", "netname", "org"):
            value = fields.get(key)
            if value:
                out.append((key, str(value)))
                break
    return out


def run_ip_asn_lookup(investigation: Investigation, policy: AcquisitionPolicy) -> list[Evidence]:
    """Look up ASN / org for each observed host, resolving DNS first if needed.

    Hostnames are skipped (not silently resolved) unless ``resolve_dns`` is
    also authorized — ADR-13: OSINT consent never implies DNS consent. The
    return value is the evidence only; the CLI surfaces skipped hosts to the
    user via :func:`dnsless_hostnames`.
    """

    from portallens.steps.dns import resolve_host
    from portallens.steps.registry import hosts_from_report

    assert_policy(policy, "use_osint_apis")
    evidence: list[Evidence] = []
    for host in hosts_from_report(investigation.report):
        if is_ip(host):
            ips = [host]
        elif policy.resolve_dns:
            ips = resolve_host(host)
        else:
            continue
        for ip in ips:
            for key, value in whois_for_ip(ip):
                evidence.append(
                    Evidence(
                        type=EvidenceType.IP_ASN,
                        source=f"ripe://{ip}",
                        key=key,
                        value=value,
                        note=f"RIPEstat whois {key} for {ip}",
                    )
                )
    return evidence


def dnsless_hostnames(investigation: Investigation, policy: AcquisitionPolicy) -> list[str]:
    """Hostnames the step would skip for lack of ``resolve_dns`` consent.

    Lets the CLI explain *why* a step produced nothing for a hostname-based
    investigation: OSINT consent (ADR-13 Tier-1) never implies DNS consent,
    so ``captive.ispman.tech`` can't be resolved-and-looked-up by a user who
    authorized only OSINT.
    """

    from portallens.steps.registry import hosts_from_report

    if policy.resolve_dns:
        return []
    return [host for host in hosts_from_report(investigation.report) if not is_ip(host)]


register_step(
    AnalysisStep(
        slug="ip_asn_lookup",
        label="Look up IP ownership / ASN via RIPEstat (OSINT)",
        requires="use_osint_apis",
        produces=(EvidenceType.IP_ASN,),
        answers=(RelationshipKind.UPSTREAM_OF,),
        run=run_ip_asn_lookup,
    )
)
