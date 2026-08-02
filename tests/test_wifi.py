"""Hardware-independent tests for the credential-free Wi-Fi core contract."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from portallens.wifi import (
    CancellationToken,
    WifiAdapter,
    WifiAdapterCapabilities,
    WifiConnection,
    WifiConnectionState,
    WifiNetwork,
    WifiOperationCancelled,
    WifiSecurity,
    ensure_capability,
)
from portallens.wifi.errors import WifiUnsupportedOperation


class TestWifiNetwork:
    def test_normalizes_scan_values_and_identity(self) -> None:
        network = WifiNetwork(
            ssid="Guest",
            security="open",
            signal_percent=120,
            bssid="AA-BB-CC-DD-EE-FF",
            interface="Wi-Fi",
        )
        assert network.security is WifiSecurity.OPEN
        assert network.signal_percent == 100
        assert network.bssid == "aa:bb:cc:dd:ee:ff"
        assert network.identity == ("Wi-Fi", "Guest", "aa:bb:cc:dd:ee:ff")

    def test_signal_is_clamped_and_hidden_network_has_safe_label(self) -> None:
        network = WifiNetwork(ssid=None, signal_percent=-10)
        assert network.signal_percent == 0
        assert network.display_name == "<hidden network>"

    def test_serialization_is_allow_listed_and_credential_free(self) -> None:
        network = WifiNetwork(
            ssid="Guest",
            security=WifiSecurity.WPA_PERSONAL,
            interface="wlan0",
        )
        serialized = network.to_dict()
        assert set(serialized) == {
            "ssid",
            "security",
            "signal_percent",
            "bssid",
            "channel",
            "interface",
            "observed_at",
        }
        assert "password" not in serialized
        assert "credentials" not in serialized

    def test_requires_timezone_aware_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            WifiNetwork(ssid="Guest", observed_at=datetime(2026, 1, 1))


class TestWifiConnection:
    def test_valid_lifecycle_is_immutable(self) -> None:
        network = WifiNetwork(ssid="Guest", security=WifiSecurity.OPEN)
        connection = WifiConnection(network=network)
        associated = connection.transition(WifiConnectionState.ASSOCIATING)
        connected = associated.transition(WifiConnectionState.CONNECTED)
        configured = connected.transition(
            WifiConnectionState.IP_CONFIGURED,
            ip_address="192.0.2.10",
            gateway="192.0.2.1",
        )
        portal = configured.transition(
            WifiConnectionState.CAPTIVE_PORTAL,
            portal_url="http://portal.example/login",
        )
        online = portal.transition(WifiConnectionState.ONLINE)
        assert connection.state is WifiConnectionState.DISCONNECTED
        assert online.state is WifiConnectionState.ONLINE
        assert online.ip_address == "192.0.2.10"
        assert online.portal_url is None

    def test_rejects_invalid_transition(self) -> None:
        connection = WifiConnection(network=WifiNetwork(ssid="Guest"))
        with pytest.raises(ValueError, match="invalid Wi-Fi transition"):
            connection.transition(WifiConnectionState.ONLINE)

    def test_non_portal_snapshot_cannot_retain_portal_url(self) -> None:
        with pytest.raises(ValueError, match="only valid for a captive-portal"):
            WifiConnection(
                network=WifiNetwork(ssid="Guest"),
                state=WifiConnectionState.CONNECTED,
                portal_url="http://portal.example/login",
            )

    def test_online_snapshot_cannot_retain_portal_url(self) -> None:
        with pytest.raises(ValueError, match="only valid for a captive-portal"):
            WifiConnection(
                network=WifiNetwork(ssid="Guest"),
                state=WifiConnectionState.ONLINE,
                portal_url="http://portal.example/login",
            )

    def test_transition_away_from_portal_clears_portal_url(self) -> None:
        connection = WifiConnection(
            network=WifiNetwork(ssid="Guest"),
            state=WifiConnectionState.CAPTIVE_PORTAL,
            portal_url="https://portal.example/login",
        )
        disconnected = connection.transition(WifiConnectionState.DISCONNECTING)
        assert disconnected.portal_url is None

    def test_connection_serialization_contains_no_credentials(self) -> None:
        connection = WifiConnection(
            network=WifiNetwork(ssid="Guest", interface="Wi-Fi"),
            state=WifiConnectionState.CAPTIVE_PORTAL,
            portal_url="https://portal.example/login?access_token=secret&session_id=abc&dst=https%3A%2F%2Fexample.test#session-secret",
            error="command output contained password=secret",
        )
        serialized = connection.to_dict()
        assert set(serialized) == {
            "network",
            "state",
            "interface",
            "ip_address",
            "gateway",
            "portal_url",
            "error",
            "observed_at",
        }
        assert serialized["interface"] == "Wi-Fi"
        assert serialized["portal_url"] == "https://portal.example/login?access_token=%5BREDACTED%5D&session_id=%5BREDACTED%5D&dst=https%3A%2F%2Fexample.test"
        assert serialized["error"] == "adapter operation failed"
        assert "secret" not in repr(serialized)
        assert "credentials" not in repr(serialized)


class TestCancellation:
    def test_token_is_pollable_and_idempotently_cancelled(self) -> None:
        token = CancellationToken()
        assert token.is_cancelled is False
        assert token.wait(0) is False
        token.cancel()
        token.cancel()
        assert token.is_cancelled is True
        assert token.wait(0) is True
        with pytest.raises(WifiOperationCancelled):
            token.raise_if_cancelled()


class TestAdapterContract:
    def test_runtime_checkable_protocol_and_capability_gate(self) -> None:
        class FakeAdapter:
            network = WifiNetwork(ssid="Fixture", interface="test0")
            capabilities = WifiAdapterCapabilities(
                platform="test",
                adapter_name="fixture",
                can_connect=False,
            )

            def scan(self, *, cancel=None):
                return ()

            def connect(self, network, *, cancel=None):
                raise AssertionError("not supported")

            def status(self, *, cancel=None):
                return WifiConnection(network=self.network)

            def disconnect(self, *, cancel=None):
                raise AssertionError("not supported")

        adapter = FakeAdapter()
        assert isinstance(adapter, WifiAdapter)
        assert adapter.scan() == ()
        assert adapter.status().network is adapter.network
        ensure_capability(adapter, "scan")
        with pytest.raises(WifiUnsupportedOperation, match="does not support connect"):
            ensure_capability(adapter, "connect")

    def test_capabilities_are_explicitly_serializable(self) -> None:
        capabilities = WifiAdapterCapabilities(
            platform="darwin",
            adapter_name="CoreWLAN",
            can_connect=True,
            notes=("requires location permission",),
        )
        assert capabilities.to_dict() == {
            "platform": "darwin",
            "adapter_name": "CoreWLAN",
            "can_scan": True,
            "can_connect": True,
            "can_disconnect": False,
            "can_status": True,
            "notes": ["requires location permission"],
        }

    def test_connection_models_have_utc_defaults(self) -> None:
        network = WifiNetwork(ssid="Guest")
        assert network.observed_at.tzinfo is timezone.utc
        assert WifiConnection(network=network).observed_at.tzinfo is timezone.utc
