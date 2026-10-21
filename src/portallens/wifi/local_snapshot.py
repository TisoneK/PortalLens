"""Read-only local network snapshot for the watched connection.

Gathers facts the host OS already knows — the associated SSID, interface
addressing, default gateway, its MAC-derived vendor, the DHCP lease, and the
DNS resolvers — through the same bounded, injectable command runner the Wi-Fi
adapters use. Nothing here sends packets; the module is strictly less network
behaviour than the connectivity probe the watch already runs.

Platform support is Windows-first (the desktop environment this tool is
developed and observed in). The collector raises
:class:`LocalSnapshotUnavailable` elsewhere so callers can record the gap
honestly instead of guessing.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from portallens.wifi.command import CommandResult, CommandRunner, SubprocessCommandRunner
from portallens.wifi.errors import WifiError


class LocalSnapshotUnavailable(WifiError):
    """The local network snapshot is not implementable on this platform."""


#: OUI prefixes (uppercase, colon-separated) recognised by the snapshot.
#: Vendor knowledge is data, not code — extend the table as operators are
#: observed (project preference: provider knowledge accumulates, it is not
#: re-derived per session).
OUI_VENDORS: dict[str, str] = {
    "DC:2C:6E": "MikroTik",
    "48:8F:5A": "MikroTik",
    "4C:5E:0C": "MikroTik",
    "E4:8D:8C": "MikroTik",
}

_WINDOWS_LEASE_FORMAT = "%A, %d %B %Y %H:%M:%S"


@dataclass(frozen=True)
class LocalNetworkSnapshot:
    """One point-in-time view of the host's side of the connection."""

    ssid: str | None = None
    interface: str | None = None
    client_ipv4: str | None = None
    gateway_ipv4: str | None = None
    gateway_mac: str | None = None
    gateway_vendor: str | None = None
    dhcp_lease_obtained: datetime | None = None
    dhcp_lease_expires: datetime | None = None
    dns_servers: tuple[str, ...] = ()
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("snapshot time must be timezone-aware")


def vendor_for_mac(mac: str | None) -> str | None:
    """Map a MAC address to a vendor via the OUI table; None when unknown."""

    if not mac:
        return None
    prefix = ":".join(mac.replace("-", ":").upper().split(":")[:3])
    return OUI_VENDORS.get(prefix)


def parse_netsh_wlan_interfaces(output: str) -> tuple[str | None, str | None]:
    """Extract (ssid, interface name) from ``netsh wlan show interfaces``.

    Both facts are absent when the radio is not associated; the parser
    returns Nones rather than failing so a wired or disconnected host still
    yields a partial snapshot.
    """

    ssid: str | None = None
    interface: str | None = None
    for raw in output.splitlines():
        if ":" not in raw:
            continue
        label, _, value = raw.partition(":")
        label = label.strip().upper()
        value = value.strip()
        if label == "SSID" and value and not value.startswith("BSSID"):
            ssid = value
        elif label == "NAME":
            interface = value
        if ssid and interface:
            break
    return ssid, interface


def parse_ipconfig_adapter(
    output: str,
    interface: str,
) -> tuple[str | None, str | None, datetime | None, datetime | None, tuple[str, ...]]:
    """Pull (client ipv4, gateway, lease obtained, lease expires, dns) for one adapter.

    ``ipconfig /all`` prints repeating dot-padded key:value blocks per
    adapter, headed by the adapter name, with long value lists (e.g. DNS
    servers) continuing onto colon-less indented lines. Lease times are
    locale-formatted ("Monday, 19 October 2026 19:05:40"); an unparseable
    locale yields None for that fact rather than a failed snapshot.
    """

    client_ipv4: str | None = None
    gateway_ipv4: str | None = None
    lease_obtained: datetime | None = None
    lease_expires: datetime | None = None
    dns_servers: list[str] = []

    section = False
    for raw in output.splitlines():
        if raw and not raw.startswith((" ", "\t")):
            # An adapter heading opens a candidate section; anything else
            # (including the global "Windows IP Configuration" banner)
            # closes it.
            section = "adapter" in raw.lower() and interface.lower() in raw.lower()
            continue
        if not section:
            continue
        label_part, sep, value = raw.partition(":")
        if not sep:
            if dns_servers:
                dns_servers.extend(v for v in raw.split() if _looks_like_ip(v))
            continue
        label = re.sub(r"^[\s.]+|[\s.]+$", "", label_part).lower()
        value = value.strip()
        if label == "ipv4 address":
            client_ipv4 = _strip_parenthetical(value)
        elif label == "default gateway" and value:
            gateway_ipv4 = value.split()[0]
        elif label == "lease obtained":
            lease_obtained = _parse_lease(value)
        elif label == "lease expires":
            lease_expires = _parse_lease(value)
        elif label == "dns servers":
            dns_servers.extend(v for v in value.split() if _looks_like_ip(v))

    return client_ipv4, gateway_ipv4, lease_obtained, lease_expires, tuple(dns_servers)


def parse_arp_mac(output: str, ip: str) -> str | None:
    """Find the neighbour MAC for ``ip`` in ``arp -a`` output."""

    for raw in output.splitlines():
        fields = raw.split()
        if len(fields) >= 2 and fields[0] == ip:
            mac = fields[1].replace("-", ":").upper()
            if re.fullmatch(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}", mac):
                return mac
    return None


def collect_local_snapshot(
    runner: CommandRunner | None = None,
    *,
    now: datetime | None = None,
) -> LocalNetworkSnapshot:
    """Gather the snapshot using the injectable command runner.

    Every individual fact degrades to None when its source is missing, so a
    partially available host still yields what it knows.
    """

    if sys.platform != "win32":
        raise LocalSnapshotUnavailable(
            f"local network snapshot is not implemented on {sys.platform} (Windows first)"
        )
    command = runner or SubprocessCommandRunner()
    observed_at = now or datetime.now(timezone.utc)

    ssid: str | None = None
    interface: str | None = None
    client_ipv4: str | None = None
    gateway_ipv4: str | None = None
    lease_obtained: datetime | None = None
    lease_expires: datetime | None = None
    dns_servers: tuple[str, ...] = ()

    try:
        netsh = command.run(["netsh", "wlan", "show", "interfaces"], timeout_seconds=10)
    except WifiError:
        netsh = CommandResult(stdout="")
    if netsh.returncode == 0:
        ssid, interface = parse_netsh_wlan_interfaces(netsh.stdout)

    if interface:
        try:
            ipconfig = command.run(["ipconfig", "/all"], timeout_seconds=10)
        except WifiError:
            ipconfig = CommandResult(stdout="")
        if ipconfig.returncode == 0:
            client_ipv4, gateway_ipv4, lease_obtained, lease_expires, dns_servers = parse_ipconfig_adapter(
                ipconfig.stdout, interface
            )

    gateway_mac: str | None = None
    if gateway_ipv4:
        try:
            arp = command.run(["arp", "-a"], timeout_seconds=10)
        except WifiError:
            arp = CommandResult(stdout="")
        if arp.returncode == 0:
            gateway_mac = parse_arp_mac(arp.stdout, gateway_ipv4)

    return LocalNetworkSnapshot(
        ssid=ssid,
        interface=interface,
        client_ipv4=client_ipv4,
        gateway_ipv4=gateway_ipv4,
        gateway_mac=gateway_mac,
        gateway_vendor=vendor_for_mac(gateway_mac),
        dhcp_lease_obtained=lease_obtained,
        dhcp_lease_expires=lease_expires,
        dns_servers=dns_servers,
        observed_at=observed_at,
    )


def snapshot_to_journal(snapshot: LocalNetworkSnapshot) -> dict[str, object]:
    """Serializable form stored on a watch journal sample."""

    return {
        "ssid": snapshot.ssid,
        "interface": snapshot.interface,
        "client_ipv4": snapshot.client_ipv4,
        "gateway_ipv4": snapshot.gateway_ipv4,
        "gateway_mac": snapshot.gateway_mac,
        "gateway_vendor": snapshot.gateway_vendor,
        "dhcp_lease_obtained": snapshot.dhcp_lease_obtained.isoformat()
        if snapshot.dhcp_lease_obtained
        else None,
        "dhcp_lease_expires": snapshot.dhcp_lease_expires.isoformat()
        if snapshot.dhcp_lease_expires
        else None,
        "dns_servers": list(snapshot.dns_servers),
        "observed_at": snapshot.observed_at.isoformat(),
    }


def snapshot_from_journal(payload: object) -> LocalNetworkSnapshot:
    """Rebuild a snapshot from :func:`snapshot_to_journal` output."""

    if not isinstance(payload, dict):
        raise ValueError("watch journal sample snapshot must be an object")
    return LocalNetworkSnapshot(
        ssid=_opt_str(payload.get("ssid")),
        interface=_opt_str(payload.get("interface")),
        client_ipv4=_opt_str(payload.get("client_ipv4")),
        gateway_ipv4=_opt_str(payload.get("gateway_ipv4")),
        gateway_mac=_opt_str(payload.get("gateway_mac")),
        gateway_vendor=_opt_str(payload.get("gateway_vendor")),
        dhcp_lease_obtained=_opt_time(payload.get("dhcp_lease_obtained")),
        dhcp_lease_expires=_opt_time(payload.get("dhcp_lease_expires")),
        dns_servers=tuple(
            v for v in (payload.get("dns_servers") or []) if isinstance(v, str)
        ),
        observed_at=_opt_time(payload.get("observed_at")) or datetime.now(timezone.utc),
    )


def _parse_lease(value: str) -> datetime | None:
    value = _strip_parenthetical(value).strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, _WINDOWS_LEASE_FORMAT)
    except ValueError:
        return None
    return parsed.astimezone()


def _strip_parenthetical(value: str) -> str:
    return re.sub(r"\(.*?\)", "", value).strip()


def _looks_like_ip(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value))


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _opt_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


__all__ = [
    "OUI_VENDORS",
    "LocalNetworkSnapshot",
    "LocalSnapshotUnavailable",
    "collect_local_snapshot",
    "parse_arp_mac",
    "parse_ipconfig_adapter",
    "parse_netsh_wlan_interfaces",
    "snapshot_from_journal",
    "snapshot_to_journal",
    "vendor_for_mac",
]
