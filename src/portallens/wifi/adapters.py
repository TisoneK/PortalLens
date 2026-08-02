"""Read-only desktop Wi-Fi discovery adapters.

The adapters intentionally expose scan and status only. Association,
credentials, packet capture, and network bypass are outside this boundary.
"""

from __future__ import annotations

import platform
import re
from collections.abc import Sequence
from dataclasses import dataclass

from portallens.wifi.adapter import WifiAdapter
from portallens.wifi.command import CommandRunner, SubprocessCommandRunner
from portallens.wifi.errors import WifiAdapterUnavailable, WifiUnsupportedOperation
from portallens.wifi.models import (
    CancellationToken,
    WifiAdapterCapabilities,
    WifiConnection,
    WifiConnectionState,
    WifiNetwork,
    WifiSecurity,
)

_DEFAULT_TIMEOUT = 10.0


def _token(cancel: CancellationToken | None) -> CancellationToken:
    return cancel if cancel is not None else CancellationToken()


def _security(value: str | None) -> WifiSecurity:
    normalized = (value or "").strip().lower()
    if not normalized or normalized in {"-", "--", "none", "open"}:
        return WifiSecurity.OPEN
    if "wep" in normalized:
        return WifiSecurity.WEP
    if any(item in normalized for item in ("enterprise", "802.1x", "eap")):
        return WifiSecurity.WPA_ENTERPRISE
    if any(item in normalized for item in ("wpa", "rsn", "psk")):
        return WifiSecurity.WPA_PERSONAL
    return WifiSecurity.UNKNOWN


def _signal(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"-?\d+", value)
    if match is None:
        return None
    number = int(match.group())
    if "dbm" in value.lower() or number < 0:
        return max(0, min(100, 2 * (number + 100)))
    return max(0, min(100, number))


def _ssid(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _network(
    *,
    ssid: str | None,
    security: str | None,
    signal: str | None = None,
    bssid: str | None = None,
    channel: str | None = None,
    interface: str | None = None,
) -> WifiNetwork:
    channel_number: int | None = None
    if channel:
        match = re.search(r"\d+", channel)
        if match:
            channel_number = int(match.group())
    return WifiNetwork(
        ssid=_ssid(ssid),
        security=_security(security),
        signal_percent=_signal(signal),
        bssid=bssid,
        channel=channel_number,
        interface=interface,
    )


def _dedupe(networks: Sequence[WifiNetwork]) -> tuple[WifiNetwork, ...]:
    result: dict[tuple[str | None, str | None, str | None], WifiNetwork] = {}
    for network in networks:
        existing = result.get(network.identity)
        if existing is None or (network.signal_percent or -1) > (existing.signal_percent or -1):
            result[network.identity] = network
    return tuple(result.values())


def _split_nmcli(line: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


def parse_nmcli_scan(output: str, *, interface: str | None = None) -> tuple[WifiNetwork, ...]:
    """Parse nmcli terse output: SSID:BSSID:SIGNAL:SECURITY."""

    networks: list[WifiNetwork] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = _split_nmcli(line)
        if len(fields) < 4:
            continue
        if len(fields) == 4:
            ssid, bssid, signal, security = fields
        else:
            # nmcli escapes delimiters inconsistently across versions. The
            # last two fields are stable, so reconstruct the BSSID from the
            # middle tail when a colon was emitted unescaped.
            ssid = fields[0]
            bssid = ":".join(fields[1:-2])
            signal, security = fields[-2:]
        networks.append(
            _network(
                ssid=ssid,
                bssid=bssid,
                signal=signal,
                security=security,
                interface=interface,
            )
        )
    return _dedupe(networks)


def parse_netsh_scan(output: str, *, interface: str | None = None) -> tuple[WifiNetwork, ...]:
    """Parse ``netsh wlan show networks mode=bssid`` output."""

    networks: list[WifiNetwork] = []
    current_ssid: str | None = None
    current_security: str | None = None
    current_bssid: str | None = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if match := re.match(r"SSID\s+\d+\s*:\s?(.*)$", line, re.IGNORECASE):
            current_ssid = match.group(1).strip() or None
            current_security = None
            current_bssid = None
        elif match := re.match(r"Authentication\s*:\s?(.*)$", line, re.IGNORECASE):
            current_security = match.group(1)
        elif match := re.match(r"BSSID\s+\d+\s*:\s?(.*)$", line, re.IGNORECASE):
            current_bssid = match.group(1).strip()
        elif match := re.match(r"Signal\s*:\s?(\d+)%", line, re.IGNORECASE):
            networks.append(
                _network(
                    ssid=current_ssid,
                    security=current_security,
                    signal=match.group(1),
                    bssid=current_bssid,
                    interface=interface,
                )
            )
    return _dedupe(networks)


def parse_airport_scan(output: str, *, interface: str | None = None) -> tuple[WifiNetwork, ...]:
    """Parse the tabular output of Apple's airport scan command."""

    networks: list[WifiNetwork] = []
    lines = [line for line in output.splitlines() if line.strip()]
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if line.startswith("WARNING:") or line.startswith("SSID"):
            continue
        fields = re.split(r"\s+", line)
        if len(fields) < 7:
            continue
        # SSID is the first column and may contain spaces; the final columns
        # are BSSID, RSSI, channel, HT, CC, security.
        bssid_index = next((index for index, item in enumerate(fields) if re.fullmatch(r"[0-9A-Fa-f:]{17}", item)), None)
        if bssid_index is None or bssid_index + 5 >= len(fields):
            continue
        networks.append(
            _network(
                ssid=" ".join(fields[:bssid_index]),
                bssid=fields[bssid_index],
                signal=fields[bssid_index + 1],
                channel=fields[bssid_index + 2],
                security=" ".join(fields[bssid_index + 5 :]),
                interface=interface,
            )
        )
    return _dedupe(networks)


def parse_networksetup_status(output: str, *, interface: str) -> WifiConnection:
    """Parse ``networksetup -getairportnetwork`` output."""

    match = re.search(r"Current Wi-Fi Network:\s*(.+)$", output, re.IGNORECASE | re.MULTILINE)
    if match is None:
        return WifiConnection(
            network=WifiNetwork(ssid=None, interface=interface),
            state=WifiConnectionState.DISCONNECTED,
            interface=interface,
        )
    return WifiConnection(
        network=WifiNetwork(ssid=match.group(1).strip(), interface=interface),
        state=WifiConnectionState.CONNECTED,
        interface=interface,
    )


def parse_nmcli_status(output: str, *, interface: str | None = None) -> WifiConnection:
    """Parse nmcli terse status output with STATE and CONNECTION fields."""

    values: dict[str, str] = {}
    for line in output.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip().upper()] = value.strip()
    connection_name = _ssid(values.get("GENERAL.CONNECTION"))
    state_value = values.get("GENERAL.STATE", "").lower()
    state = (
        WifiConnectionState.CONNECTED
        if "connected" in state_value and "disconnected" not in state_value
        else WifiConnectionState.DISCONNECTED
    )
    return WifiConnection(
        network=WifiNetwork(ssid=connection_name, interface=interface),
        state=state,
        interface=interface,
    )


def parse_netsh_status(output: str) -> WifiConnection:
    """Parse ``netsh wlan show interfaces`` output."""

    values: dict[str, str] = {}
    for raw_line in output.splitlines():
        if ":" in raw_line:
            key, value = raw_line.split(":", 1)
            values[key.strip().lower()] = value.strip()
    interface = values.get("name")
    ssid = _ssid(values.get("ssid"))
    state = WifiConnectionState.CONNECTED if values.get("state", "").lower() == "connected" else WifiConnectionState.DISCONNECTED
    return WifiConnection(
        network=WifiNetwork(ssid=ssid, interface=interface),
        state=state,
        interface=interface,
    )


@dataclass
class _ReadOnlyAdapter:
    runner: CommandRunner
    timeout_seconds: float = _DEFAULT_TIMEOUT

    @property
    def capabilities(self) -> WifiAdapterCapabilities:
        return WifiAdapterCapabilities(
            platform=self.platform,
            adapter_name=self.adapter_name,
            can_scan=True,
            can_connect=False,
            can_disconnect=False,
            can_status=True,
            notes=("read-only discovery; connection is delegated to the host OS",),
        )

    @property
    def platform(self) -> str:
        raise NotImplementedError

    @property
    def adapter_name(self) -> str:
        raise NotImplementedError

    def connect(self, network: WifiNetwork, *, cancel: CancellationToken | None = None) -> WifiConnection:
        del network
        _token(cancel).raise_if_cancelled()
        raise WifiUnsupportedOperation("read-only Wi-Fi adapter does not connect to networks")

    def disconnect(self, *, cancel: CancellationToken | None = None) -> WifiConnection:
        _token(cancel).raise_if_cancelled()
        raise WifiUnsupportedOperation("read-only Wi-Fi adapter does not disconnect from networks")


@dataclass
class WindowsWifiAdapter(_ReadOnlyAdapter):
    interface: str | None = None

    @property
    def platform(self) -> str:
        return "windows"

    @property
    def adapter_name(self) -> str:
        return "netsh"

    def scan(self, *, cancel: CancellationToken | None = None) -> Sequence[WifiNetwork]:
        _token(cancel).raise_if_cancelled()
        result = self.runner.run(("netsh", "wlan", "show", "networks", "mode=bssid"), timeout_seconds=self.timeout_seconds, cancel=cancel)
        _token(cancel).raise_if_cancelled()
        return parse_netsh_scan(result.stdout, interface=self.interface)

    def status(self, *, cancel: CancellationToken | None = None) -> WifiConnection:
        _token(cancel).raise_if_cancelled()
        result = self.runner.run(("netsh", "wlan", "show", "interfaces"), timeout_seconds=self.timeout_seconds, cancel=cancel)
        _token(cancel).raise_if_cancelled()
        return parse_netsh_status(result.stdout)


@dataclass
class MacOSWifiAdapter(_ReadOnlyAdapter):
    interface: str = "en0"
    airport_path: str = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"

    @property
    def platform(self) -> str:
        return "darwin"

    @property
    def adapter_name(self) -> str:
        return "airport/networksetup"

    def scan(self, *, cancel: CancellationToken | None = None) -> Sequence[WifiNetwork]:
        _token(cancel).raise_if_cancelled()
        result = self.runner.run((self.airport_path, "-s"), timeout_seconds=self.timeout_seconds, cancel=cancel)
        _token(cancel).raise_if_cancelled()
        return parse_airport_scan(result.stdout, interface=self.interface)

    def status(self, *, cancel: CancellationToken | None = None) -> WifiConnection:
        _token(cancel).raise_if_cancelled()
        result = self.runner.run(("networksetup", "-getairportnetwork", self.interface), timeout_seconds=self.timeout_seconds, cancel=cancel)
        _token(cancel).raise_if_cancelled()
        return parse_networksetup_status(result.stdout, interface=self.interface)


@dataclass
class LinuxWifiAdapter(_ReadOnlyAdapter):
    interface: str | None = None

    @property
    def platform(self) -> str:
        return "linux"

    @property
    def adapter_name(self) -> str:
        return "nmcli"

    def scan(self, *, cancel: CancellationToken | None = None) -> Sequence[WifiNetwork]:
        _token(cancel).raise_if_cancelled()
        args = ("nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,SECURITY", "dev", "wifi")
        result = self.runner.run(args, timeout_seconds=self.timeout_seconds, cancel=cancel)
        _token(cancel).raise_if_cancelled()
        return parse_nmcli_scan(result.stdout, interface=self.interface)

    def status(self, *, cancel: CancellationToken | None = None) -> WifiConnection:
        _token(cancel).raise_if_cancelled()
        args: tuple[str, ...] = (
            "nmcli",
            "-t",
            "-f",
            "GENERAL.STATE,GENERAL.CONNECTION",
            "dev",
            "show",
        )
        if self.interface is not None:
            args += (self.interface,)
        result = self.runner.run(args, timeout_seconds=self.timeout_seconds, cancel=cancel)
        _token(cancel).raise_if_cancelled()
        return parse_nmcli_status(result.stdout, interface=self.interface)


def adapter_for_platform(
    system: str | None = None,
    *,
    runner: CommandRunner | None = None,
    interface: str | None = None,
) -> WifiAdapter:
    """Create the read-only adapter matching a desktop platform name."""

    platform_name = (system or platform.system()).lower()
    selected_runner = runner or SubprocessCommandRunner()
    if platform_name in {"windows", "win32"}:
        return WindowsWifiAdapter(selected_runner, interface=interface)
    if platform_name in {"darwin", "mac", "macos"}:
        return MacOSWifiAdapter(selected_runner, interface=interface or "en0")
    if platform_name == "linux":
        return LinuxWifiAdapter(selected_runner, interface=interface)
    raise WifiAdapterUnavailable(f"unsupported Wi-Fi platform: {system or platform.system()}")


__all__ = [
    "LinuxWifiAdapter",
    "MacOSWifiAdapter",
    "WindowsWifiAdapter",
    "adapter_for_platform",
    "parse_airport_scan",
    "parse_netsh_scan",
    "parse_netsh_status",
    "parse_networksetup_status",
    "parse_nmcli_scan",
    "parse_nmcli_status",
]
