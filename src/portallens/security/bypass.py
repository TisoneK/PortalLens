"""Bounded captive-portal bypass detection probes.

These probes answer only whether a bypass condition appears possible. They do
not authenticate, submit credentials, alter server state, or grant access.
Every active probe requires ``AcquisitionPolicy(authorized=True)`` and has a
small bounded target/port surface. Network functions are injectable so callers
and tests can use a controlled capture instead of touching a live network.
"""

from __future__ import annotations

import socket
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse, urlunparse

from portallens.acquisition import assert_policy
from portallens.acquisition.fetcher import FetchedDocument, fetch
from portallens.evidence import Evidence, EvidenceType
from portallens.portal import AcquisitionPolicy


@dataclass(frozen=True)
class ProbeResponse:
    """Small response shape shared by HTTP-based bypass probes."""

    status_code: int
    final_url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: str = ""


@dataclass(frozen=True)
class ConnectResult:
    """The parsed result of an HTTP CONNECT attempt."""

    status_code: int | None
    reason: str = ""


Request = Callable[[str], ProbeResponse]
ConnectRequest = Callable[[str, str, float], ConnectResult]
Resolve = Callable[[str], Sequence[str]]
ProbePort = Callable[[str, int], bool]

# Keep the default probes useful but deliberately small and predictable.
DEFAULT_BYPASS_PORTS: tuple[int, ...] = (53, 80, 443, 8080, 8443)
MAX_BYPASS_PORTS = 16
MAX_TAMPER_PARAMETERS = 4
_SAFE_TAMPER_PARAMETERS = frozenset(
    {"dst", "link-orig", "redirect", "redirect_uri", "continue", "return", "url", "next"}
)
_SENSITIVE_PARAMETERS = frozenset(
    {"password", "passwd", "pass", "token", "secret", "voucher", "credential", "otp"}
)


def connect_test(
    proxy: str,
    target: str,
    policy: AcquisitionPolicy,
    *,
    connect_request: ConnectRequest | None = None,
    timeout_seconds: float = 2.0,
) -> list[Evidence]:
    """Test whether an HTTP proxy/gateway permits a CONNECT tunnel.

    A successful 2xx CONNECT response is evidence of possible tunnel bypass;
    redirects, authentication challenges, refusals, malformed responses, and
    transport errors are recorded as negative evidence. The default sends one
    standards-compliant CONNECT request and reads only the response headers.
    """

    assert_policy(policy, "connect_test")
    target_host, target_port = _target_host_port(target)
    if not proxy.strip():
        raise ValueError("proxy must not be empty")
    request = connect_request or _http_connect
    source = f"connect://{_display_endpoint(proxy)}/{target_host}:{target_port}"
    try:
        result = request(proxy, f"{target_host}:{target_port}", timeout_seconds)
        allowed = result.status_code is not None and 200 <= result.status_code < 300
        status = str(result.status_code) if result.status_code is not None else "transport-error"
        return [
            _evidence(
                EvidenceType.BYPASS_CONNECT,
                source,
                "connect:allowed" if allowed else "connect:blocked",
                f"{'allowed' if allowed else 'blocked'} ({status})",
                "A 2xx CONNECT response indicates the gateway permitted a tunnel; "
                "this test did not send application data through it.",
            )
        ]
    except (OSError, ValueError) as exc:
        return [
            _evidence(
                EvidenceType.BYPASS_CONNECT,
                source,
                "connect:blocked",
                "blocked (transport error)",
                f"CONNECT could not establish a tunnel: {type(exc).__name__}.",
            )
        ]


def dns_tunnel_test(
    hostname: str,
    policy: AcquisitionPolicy,
    *,
    resolve: Resolve | None = None,
    captive_addresses: Sequence[str] = (),
) -> list[Evidence]:
    """Test whether DNS queries for an external name pass through normally.

    The default resolver performs one bounded A/AAAA lookup. A caller doing a
    controlled tunnel test can inject a resolver for a unique name under its
    own domain and compare the returned marker/address. A successful answer
    is only *potential* bypass evidence; DNS resolution alone does not prove
    arbitrary traffic is allowed.
    """

    assert_policy(policy, "dns_tunnel_test")
    if not hostname.strip() or any(ch.isspace() for ch in hostname):
        raise ValueError("hostname must be a non-empty DNS name")
    _host_from_value(hostname)
    resolve_name = resolve or _resolve
    source = f"dns://{hostname}"
    try:
        answers = tuple(str(answer) for answer in resolve_name(hostname))
    except (OSError, ValueError):
        answers = ()
    captive = {str(address) for address in captive_addresses}
    allowed = bool(answers) and not (captive and set(answers) <= captive)
    value = f"{'resolved' if allowed else 'blocked'} ({', '.join(answers) or 'no answer'})"
    return [
        _evidence(
            EvidenceType.BYPASS_DNS,
            source,
            "dns_tunnel:allowed" if allowed else "dns_tunnel:blocked",
            value,
            "A normal answer can indicate DNS is not being walled-gardened. "
            "Use a controlled unique name for a definitive tunnel test.",
        )
    ]


def click_through_test(
    target_url: str,
    portal_host: str,
    policy: AcquisitionPolicy,
    *,
    request: Request | None = None,
) -> list[Evidence]:
    """Test whether a request reaches the intended site instead of the portal.

    Redirects are followed by the default authorized fetcher. A successful
    response whose final host is not the captive portal host is reported as
    potential click-through bypass evidence. No login or form submission is
    performed.
    """

    assert_policy(policy, "click_through_test")
    target = urlparse(target_url)
    if not target.hostname:
        raise ValueError("target_url must contain a hostname")
    if not portal_host.strip():
        raise ValueError("portal_host must not be empty")
    portal = _host_from_value(portal_host)
    make_request = request or _fetch_response(policy)
    source = f"click-through://{target.hostname}"
    try:
        response = make_request(target_url)
        final_host = (urlparse(response.final_url).hostname or "").lower()
        reached_target = final_host == target.hostname.lower().rstrip(".")
        allowed = reached_target and response.status_code < 400 and final_host != portal
        return [
            _evidence(
                EvidenceType.BYPASS_CLICK_THROUGH,
                source,
                "click_through:allowed" if allowed else "click_through:blocked",
                f"{'reached target' if allowed else 'stopped at portal'} "
                f"(status {response.status_code}, final host {final_host or 'unknown'})",
                "The test performed a single GET with redirects and did not submit credentials.",
            )
        ]
    except (OSError, ValueError) as exc:
        return [
            _evidence(
                EvidenceType.BYPASS_CLICK_THROUGH,
                source,
                "click_through:blocked",
                "blocked (transport error)",
                f"Click-through request failed: {type(exc).__name__}.",
            )
        ]


def port_scan_test(
    host: str,
    policy: AcquisitionPolicy,
    *,
    ports: Sequence[int] = DEFAULT_BYPASS_PORTS,
    probe_port: ProbePort | None = None,
    max_ports: int = MAX_BYPASS_PORTS,
) -> list[Evidence]:
    """Check a bounded list of common egress/service ports.

    Open ports are potential bypass evidence only: reachability does not
    establish that application traffic is unauthenticated. At most
    ``max_ports`` ports are checked, and the default never scans a range.
    """

    assert_policy(policy, "bypass_port_scan")
    normalized_host = _host_from_value(host)
    selected = _validate_ports(ports, max_ports)
    probe = probe_port or _socket_probe
    evidence: list[Evidence] = []
    for port in selected:
        try:
            is_open = bool(probe(normalized_host, port))
        except OSError:
            is_open = False
        evidence.append(
            _evidence(
                EvidenceType.BYPASS_PORT,
                f"port-scan://{normalized_host}:{port}",
                "port_scan:open" if is_open else "port_scan:closed",
                f"{'open' if is_open else 'closed'} ({port})",
                "Port reachability is a transport-level signal; no payload was sent.",
            )
        )
    return evidence


def parameter_tampering_test(
    portal_url: str,
    policy: AcquisitionPolicy,
    *,
    parameters: Sequence[str] | None = None,
    request: Request | None = None,
    sentinel: str = "https://example.com/portallens-bypass-check",
) -> list[Evidence]:
    """Safely compare a portal response with benign URL-parameter mutations.

    The baseline and each mutation are ordinary GET requests to the supplied
    portal host. Only navigation-like parameters are selected by default;
    credential, voucher, token, and secret fields are rejected. A mutation is
    positive when it reaches a non-portal final host with a successful status.
    No exploit payload or credential is generated.
    """

    assert_policy(policy, "parameter_tampering_test")
    parsed = urlparse(portal_url)
    if not parsed.hostname:
        raise ValueError("portal_url must contain a hostname")
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    available = [key for key, _ in pairs if key.lower() in _SAFE_TAMPER_PARAMETERS]
    selected = list(parameters) if parameters is not None else available
    if not selected:
        return [
            _evidence(
                EvidenceType.BYPASS_PARAMETER,
                f"parameter-tamper://{parsed.hostname}",
                "parameter_tampering:inconclusive",
                "inconclusive (no safe navigation parameters)",
                "No supported navigation parameter was present; no mutation was sent.",
            )
        ]
    if len(selected) > MAX_TAMPER_PARAMETERS:
        raise ValueError(f"at most {MAX_TAMPER_PARAMETERS} parameters may be tested")
    for key in selected:
        if key.lower() in _SENSITIVE_PARAMETERS:
            raise ValueError(f"refusing to tamper with sensitive parameter {key!r}")
        if key.lower() not in _SAFE_TAMPER_PARAMETERS:
            raise ValueError(f"refusing to mutate non-navigation parameter {key!r}")
        if key not in {name for name, _ in pairs}:
            raise ValueError(f"parameter {key!r} is not present in portal_url")

    make_request = request or _fetch_response(policy)
    try:
        baseline = make_request(portal_url)
    except (OSError, ValueError):
        baseline = None
    portal = parsed.hostname.lower().rstrip(".")
    baseline_host = (
        (urlparse(baseline.final_url).hostname or "").lower().rstrip(".")
        if baseline is not None
        else ""
    )
    baseline_blocked = baseline is not None and (
        baseline_host == portal or baseline.status_code >= 400
    )
    evidence: list[Evidence] = []
    for key in selected:
        mutated = _replace_query_parameter(parsed, key, sentinel)
        try:
            response = make_request(mutated)
            final_host = (urlparse(response.final_url).hostname or "").lower().rstrip(".")
            allowed = (
                baseline_blocked
                and final_host not in {"", portal}
                and response.status_code < 400
            )
            value = (
                f"possible bypass (status {response.status_code}, final host {final_host})"
                if allowed
                else f"blocked (status {response.status_code}, final host {final_host or 'unknown'})"
            )
        except (OSError, ValueError) as exc:
            allowed = False
            value = f"blocked (transport error: {type(exc).__name__})"
        evidence.append(
            _evidence(
                EvidenceType.BYPASS_PARAMETER,
                f"parameter-tamper://{portal}/{key}",
                "parameter_tampering:possible" if allowed else "parameter_tampering:blocked",
                value,
                "Compared with a baseline portal GET; the mutation used a benign sentinel and "
                f"baseline was {'blocked' if baseline_blocked else 'not blocked or unavailable'}.",
            )
        )
    return evidence


def _target_host_port(target: str) -> tuple[str, int]:
    parsed = urlparse(target if "://" in target else f"//{target}")
    if not parsed.hostname:
        raise ValueError("target must contain a hostname")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("target has an invalid port") from exc
    return parsed.hostname, port


def _display_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint if "://" in endpoint else f"//{endpoint}")
    return parsed.netloc or parsed.path


def _http_connect(proxy: str, target: str, timeout: float) -> ConnectResult:
    parsed = urlparse(proxy if "://" in proxy else f"//{proxy}")
    if not parsed.hostname:
        raise ValueError("proxy must contain a hostname")
    port = parsed.port or 8080
    with socket.create_connection((parsed.hostname, port), timeout=timeout) as sock:
        sock.sendall(
            f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
            "Proxy-Connection: Keep-Alive\r\n\r\n".encode("ascii")
        )
        raw = sock.recv(8192).split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
    parts = raw.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise ValueError("malformed CONNECT response")
    return ConnectResult(status_code=int(parts[1]), reason=parts[2] if len(parts) > 2 else "")


def _resolve(hostname: str) -> Sequence[str]:
    return tuple({str(info[4][0]) for info in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)})


def _fetch_response(policy: AcquisitionPolicy) -> Request:
    def request(url: str) -> ProbeResponse:
        response: FetchedDocument = fetch(url, policy)
        return ProbeResponse(
            status_code=response.status_code,
            final_url=response.final_url,
            headers=response.headers,
            body=response.body,
        )

    return request


def _socket_probe(host: str, port: int) -> bool:
    with socket.create_connection((host, port), timeout=2.0):
        return True


def _validate_ports(ports: Sequence[int], max_ports: int) -> tuple[int, ...]:
    if max_ports < 1 or max_ports > MAX_BYPASS_PORTS:
        raise ValueError(f"max_ports must be between 1 and {MAX_BYPASS_PORTS}")
    selected = tuple(dict.fromkeys(ports))
    if len(selected) > max_ports:
        raise ValueError(f"at most {max_ports} ports may be tested")
    if any(not isinstance(port, int) or not 1 <= port <= 65535 for port in selected):
        raise ValueError("ports must be integers between 1 and 65535")
    return selected


def _replace_query_parameter(parsed: ParseResult, key: str, value: str) -> str:
    pairs = [(name, value if name == key else current) for name, current in parse_qsl(parsed.query, keep_blank_values=True)]
    return urlunparse(parsed._replace(query=urlencode(pairs, doseq=True)))


def _host_from_value(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"//{value}")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("host value must contain a hostname")
    return host


def _evidence(
    evidence_type: EvidenceType,
    source: str,
    key: str,
    value: str,
    note: str,
) -> Evidence:
    return Evidence(type=evidence_type, source=source, key=key, value=value, note=note)
