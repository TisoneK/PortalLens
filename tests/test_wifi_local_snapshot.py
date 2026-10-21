"""Tests for the read-only local network snapshot.

Parser fixtures are the real command shapes observed on the development
workstation (sanitized of nothing — they carry no secrets, only the host's
own interface facts), so the parsers are pinned to what Windows actually
prints, including dot-padded labels and colon-less DNS continuation lines.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from portallens.wifi.command import CommandResult
from portallens.wifi.local_snapshot import (
    LocalNetworkSnapshot,
    LocalSnapshotUnavailable,
    collect_local_snapshot,
    parse_arp_mac,
    parse_ipconfig_adapter,
    parse_netsh_wlan_interfaces,
    snapshot_from_journal,
    snapshot_to_journal,
    vendor_for_mac,
)

NETSH_INTERFACES = """\
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wireless-AC 9260 160MHz
    GUID                   : 454e1c9a-634b-47a2-b268-5e1e3289a8f5
    Physical address       : 98:af:65:7c:6a:69
    Interface type         : Primary
    State                  : connected
    SSID                   : KITENGELA@10
    AP BSSID               : 8c:83:e8:0f:df:7d
    Band                   : 5 GHz
"""

IPCONFIG_ALL = """\
Windows IP Configuration

   Host Name . . . . . . . . . . : workstation
   DNS Servers . . . . . . . . : 192.168.1.1

Ethernet adapter Ethernet:

   Media State . . . . . . . . . . . . . : Media disconnected

Wireless LAN adapter Local Area Connection* 2:

   Description . . . . . . . . . . . . . : Microsoft Wi-Fi Direct Virtual Adapter #2
   IPv4 Address. . . . . . . . . . . . . . : 192.168.137.1(Preferred)
   Default Gateway . . . . . . . . . . . : 192.168.137.1

Wireless LAN adapter Wi-Fi:

   Connection-specific DNS Suffix  . :
   Description . . . . . . . . . . . . : Intel(R) Wireless-AC 9260 160MHz
   Physical Address. . . . . . . . . : 98-AF-65-7C-6A-69
   DHCP Enabled. . . . . . . . . . . . . : Yes
   IPv4 Address. . . . . . . . . : 11.220.2.109(Preferred)
   Subnet Mask . . . . . . . : 255.255.0.0
   Lease Obtained. . . . . . : Monday, 19 October 2026 19:05:40
   Lease Expires . . . . . . : Thursday, 22 October 2026 07:55:15
   Default Gateway . . . . . : 11.220.0.1
   DHCP Server . . . . . . : 11.220.0.1
   DNS Servers . . . . . : 8.8.8.8
                                       192.168.100.1
   NetBIOS over Tcpip. . . . : Enabled
"""

ARP_OUTPUT = """\
Interface: 11.220.2.109 --- 0xb
  Internet Address      Physical Address      Type
  11.220.0.1            dc-2c-6e-00-06-8c     dynamic
  11.220.2.1            8c-83-e8-0f-df-7d     dynamic
"""


class FakeRunner:
    """Returns canned output per command, recording what was asked."""

    def __init__(self, responses: dict[tuple[str, ...], str]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, *, timeout_seconds, cancel=None):
        self.calls.append(tuple(args))
        stdout = self.responses.get(tuple(args), "")
        return CommandResult(stdout=stdout)


class TestNetshParsing:
    def test_connected_interface_yields_ssid_and_name(self) -> None:
        ssid, interface = parse_netsh_wlan_interfaces(NETSH_INTERFACES)
        assert ssid == "KITENGELA@10"
        assert interface == "Wi-Fi"

    def test_disconnected_radio_yields_nones(self) -> None:
        output = "There is 1 interface on the system.\n\n    Name : Wi-Fi\n    State : disconnected\n"
        assert parse_netsh_wlan_interfaces(output) == (None, "Wi-Fi")


class TestIpConfigParsing:
    def test_wifi_adapter_facts_extracted(self) -> None:
        client, gateway, obtained, expires, dns = parse_ipconfig_adapter(IPCONFIG_ALL, "Wi-Fi")
        assert client == "11.220.2.109"
        assert gateway == "11.220.0.1"
        assert obtained == datetime(2026, 10, 19, 19, 5, 40).astimezone()
        assert expires == datetime(2026, 10, 22, 7, 55, 15).astimezone()
        assert dns == ("8.8.8.8", "192.168.100.1")

    def test_other_adapters_are_ignored(self) -> None:
        client, gateway, *_ = parse_ipconfig_adapter(IPCONFIG_ALL, "Ethernet")
        assert client is None
        assert gateway is None

    def test_unknown_interface_yields_nothing(self) -> None:
        results = parse_ipconfig_adapter(IPCONFIG_ALL, "Bogus")
        assert results == (None, None, None, None, ())


class TestArpParsing:
    def test_gateway_mac_found_and_normalized(self) -> None:
        assert parse_arp_mac(ARP_OUTPUT, "11.220.0.1") == "DC:2C:6E:00:06:8C"

    def test_unknown_ip_yields_none(self) -> None:
        assert parse_arp_mac(ARP_OUTPUT, "10.9.9.9") is None


class TestVendorLookup:
    def test_known_mikrotik_oui(self) -> None:
        assert vendor_for_mac("dc-2c-6e-00-06-8c") == "MikroTik"
        assert vendor_for_mac("DC:2C:6E:00:06:8C") == "MikroTik"

    def test_unknown_prefix_yields_none(self) -> None:
        assert vendor_for_mac("8C:83:E8:0F:DF:7D") is None
        assert vendor_for_mac(None) is None


class TestCollectSnapshot:
    def test_full_snapshot_from_canned_commands(self) -> None:
        runner = FakeRunner(
            {
                ("netsh", "wlan", "show", "interfaces"): NETSH_INTERFACES,
                ("ipconfig", "/all"): IPCONFIG_ALL,
                ("arp", "-a"): ARP_OUTPUT,
            }
        )
        snapshot = collect_local_snapshot(runner, now=datetime(2026, 10, 21, 5, 20, tzinfo=timezone.utc))

        assert snapshot.ssid == "KITENGELA@10"
        assert snapshot.interface == "Wi-Fi"
        assert snapshot.client_ipv4 == "11.220.2.109"
        assert snapshot.gateway_ipv4 == "11.220.0.1"
        assert snapshot.gateway_mac == "DC:2C:6E:00:06:8C"
        assert snapshot.gateway_vendor == "MikroTik"
        assert snapshot.dhcp_lease_obtained is not None
        assert snapshot.dhcp_lease_expires is not None
        assert snapshot.dns_servers == ("8.8.8.8", "192.168.100.1")
        assert snapshot.observed_at == datetime(2026, 10, 21, 5, 20, tzinfo=timezone.utc)

    def test_failing_commands_degrade_to_none_facts(self) -> None:
        runner = FakeRunner({("netsh", "wlan", "show", "interfaces"): "garbage"})
        snapshot = collect_local_snapshot(runner)
        assert snapshot.ssid is None
        assert snapshot.gateway_ipv4 is None
        assert snapshot.gateway_vendor is None
        assert snapshot.dns_servers == ()

    def test_non_windows_host_raises_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.platform", "linux")
        with pytest.raises(LocalSnapshotUnavailable):
            collect_local_snapshot(FakeRunner({}))


class TestSnapshotJournal:
    def test_round_trip_preserves_facts(self) -> None:
        snapshot = LocalNetworkSnapshot(
            ssid="KITENGELA@10",
            interface="Wi-Fi",
            client_ipv4="11.220.2.109",
            gateway_ipv4="11.220.0.1",
            gateway_mac="DC:2C:6E:00:06:8C",
            gateway_vendor="MikroTik",
            dhcp_lease_obtained=datetime(2026, 10, 19, 19, 5, 40, tzinfo=timezone.utc),
            dhcp_lease_expires=datetime(2026, 10, 22, 7, 55, 15, tzinfo=timezone.utc),
            dns_servers=("8.8.8.8", "192.168.100.1"),
            observed_at=datetime(2026, 10, 21, 5, 20, tzinfo=timezone.utc),
        )
        restored = snapshot_from_journal(snapshot_to_journal(snapshot))
        assert restored == snapshot

    def test_non_object_payload_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be an object"):
            snapshot_from_journal(["not", "a", "dict"])
