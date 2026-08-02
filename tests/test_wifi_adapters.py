"""Fixture-driven tests for read-only desktop Wi-Fi adapters."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from portallens.wifi import (
    CancellationToken,
    CommandResult,
    LinuxWifiAdapter,
    MacOSWifiAdapter,
    WifiAdapterUnavailable,
    WifiConnectionState,
    WifiOperationCancelled,
    WifiUnsupportedOperation,
    WindowsWifiAdapter,
    adapter_for_platform,
    ensure_capability,
    parse_airport_scan,
    parse_netsh_scan,
    parse_netsh_status,
    parse_networksetup_status,
    parse_nmcli_scan,
    parse_nmcli_status,
)
from portallens.wifi.command import SubprocessCommandRunner

NETSH_SCAN = """
There are 2 networks currently visible.

SSID 1 : MAXY PRIST 13 @8bob
    Network type            : Infrastructure
    Authentication          : Open
    Encryption              : None
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 72%
         Radio type         : 802.11n

SSID 2 : Secure Guest
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : aa:bb:cc:dd:ee:02
         Signal             : 44%
         Radio type         : 802.11ac
"""

AIRPORT_SCAN = """
                            SSID BSSID             RSSI CHANNEL HT CC SECURITY
                     Guest Cafe aa:bb:cc:dd:ee:03 -55 11      Y  US WPA2(PSK/AES/AES)
                       Open Wifi aa:bb:cc:dd:ee:04 -80 6       Y  -- NONE
"""

NMCLI_SCAN = """
Guest\\: Cafe:aa:bb:cc:dd:ee:05:83:WPA2
Open Wifi:aa:bb:cc:dd:ee:06:35:
"""


@dataclass
class FixtureRunner:
    result: CommandResult

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.cancellations: list[CancellationToken | None] = []

    def run(self, args, *, timeout_seconds, cancel=None):
        del timeout_seconds
        self.calls.append(tuple(args))
        self.cancellations.append(cancel)
        if cancel is not None:
            cancel.raise_if_cancelled()
        return self.result


class TestParsers:
    def test_netsh_parser_preserves_bssid_and_maps_security(self) -> None:
        networks = parse_netsh_scan(NETSH_SCAN, interface="Wi-Fi")
        assert len(networks) == 2
        assert networks[0].ssid == "MAXY PRIST 13 @8bob"
        assert networks[0].bssid == "aa:bb:cc:dd:ee:01"
        assert networks[0].signal_percent == 72
        assert networks[0].security.value == "open"
        assert networks[1].security.value == "wpa_personal"

    def test_airport_parser_converts_dbm_and_handles_spaces(self) -> None:
        networks = parse_airport_scan(AIRPORT_SCAN, interface="en0")
        assert len(networks) == 2
        assert networks[0].ssid == "Guest Cafe"
        assert networks[0].signal_percent == 90
        assert networks[0].channel == 11
        assert networks[0].security.value == "wpa_personal"
        assert networks[1].security.value == "open"

    def test_nmcli_parser_unescapes_colons_and_normalizes_signal(self) -> None:
        networks = parse_nmcli_scan(NMCLI_SCAN, interface="wlan0")
        assert [network.ssid for network in networks] == ["Guest: Cafe", "Open Wifi"]
        assert networks[0].signal_percent == 83
        assert networks[0].security.value == "wpa_personal"
        assert networks[1].security.value == "open"

    def test_status_parsers_report_connected_or_disconnected(self) -> None:
        windows = parse_netsh_status("""
Name                   : Wi-Fi
State                  : connected
SSID                   : Guest Cafe
""")
        mac = parse_networksetup_status("Current Wi-Fi Network: Guest Cafe", interface="en0")
        linux = parse_nmcli_status("GENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:Guest Cafe", interface="wlan0")
        disconnected = parse_networksetup_status("You are not associated with an AirPort network.", interface="en0")
        linux_disconnected = parse_nmcli_status("GENERAL.STATE:30 (disconnected)\nGENERAL.CONNECTION:", interface="wlan0")
        assert windows.state is WifiConnectionState.CONNECTED
        assert windows.network.ssid == "Guest Cafe"
        assert mac.state is WifiConnectionState.CONNECTED
        assert linux.state is WifiConnectionState.CONNECTED
        assert disconnected.state is WifiConnectionState.DISCONNECTED
        assert linux_disconnected.state is WifiConnectionState.DISCONNECTED


class TestAdapters:
    def test_windows_adapter_is_read_only_and_uses_expected_command(self) -> None:
        runner = FixtureRunner(CommandResult(NETSH_SCAN))
        adapter = WindowsWifiAdapter(runner, interface="Wi-Fi")
        networks = adapter.scan()
        assert len(networks) == 2
        assert runner.calls == [("netsh", "wlan", "show", "networks", "mode=bssid")]
        assert adapter.capabilities.can_connect is False
        with pytest.raises(WifiUnsupportedOperation):
            ensure_capability(adapter, "connect")

    def test_macos_and_linux_adapters_use_injected_runner(self) -> None:
        mac_runner = FixtureRunner(CommandResult(AIRPORT_SCAN))
        mac = MacOSWifiAdapter(mac_runner, interface="en1", airport_path="airport")
        assert mac.scan()[0].interface == "en1"
        assert mac_runner.calls == [("airport", "-s")]

        linux_runner = FixtureRunner(CommandResult(NMCLI_SCAN))
        linux = LinuxWifiAdapter(linux_runner, interface="wlan0")
        assert linux.scan()[0].ssid == "Guest: Cafe"
        assert linux_runner.calls == [("nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,SECURITY", "dev", "wifi")]
        status_runner = FixtureRunner(CommandResult("GENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:Guest Cafe"))
        LinuxWifiAdapter(status_runner, interface="wlan0").status()
        assert status_runner.calls == [
            ("nmcli", "-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION", "dev", "show", "wlan0")
        ]

    def test_platform_factory_selects_supported_adapters(self) -> None:
        assert isinstance(adapter_for_platform("Windows", runner=FixtureRunner(CommandResult(""))), WindowsWifiAdapter)
        assert isinstance(adapter_for_platform("Darwin", runner=FixtureRunner(CommandResult(""))), MacOSWifiAdapter)
        assert isinstance(adapter_for_platform("Linux", runner=FixtureRunner(CommandResult(""))), LinuxWifiAdapter)
        with pytest.raises(WifiAdapterUnavailable, match="unsupported"):
            adapter_for_platform("Plan9", runner=FixtureRunner(CommandResult("")))

    def test_cancelled_operation_is_forwarded_before_runner(self) -> None:
        token = CancellationToken()
        token.cancel()
        runner = FixtureRunner(CommandResult(NETSH_SCAN))
        with pytest.raises(WifiOperationCancelled):
            WindowsWifiAdapter(runner).scan(cancel=token)
        assert runner.calls == []

    def test_connect_and_disconnect_are_explicitly_unavailable(self) -> None:
        adapter = LinuxWifiAdapter(FixtureRunner(CommandResult("")))
        with pytest.raises(WifiUnsupportedOperation, match="does not connect"):
            adapter.connect(parse_nmcli_scan(NMCLI_SCAN)[0])
        with pytest.raises(WifiUnsupportedOperation, match="does not disconnect"):
            adapter.disconnect()


class TestCommandRunner:
    def test_empty_command_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            SubprocessCommandRunner().run((), timeout_seconds=1)

    def test_missing_command_maps_to_typed_unavailable_error(self) -> None:
        with pytest.raises(WifiAdapterUnavailable, match="unavailable"):
            SubprocessCommandRunner().run(("portallens-command-that-does-not-exist",), timeout_seconds=1)
