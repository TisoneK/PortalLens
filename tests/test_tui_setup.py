"""Tests for the primary setup screen launched by bare ``portallens``."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event

import pytest
from click.testing import CliRunner

from portallens.cli import main
from portallens.wifi import (
    CancellationToken,
    WifiAdapterCapabilities,
    WifiConnection,
    WifiConnectionState,
    WifiNetwork,
    WifiSecurity,
)
from portallens.wifi.errors import WifiOperationCancelled
from portallens.wifi.session import WifiPickerPhase, WifiPickerState, WifiSessionController


@dataclass
class SetupAdapter:
    """Hardware-free adapter for setup-screen tests."""

    network: WifiNetwork

    def __post_init__(self) -> None:
        self.capabilities = WifiAdapterCapabilities(
            platform="test",
            adapter_name="fixture",
            can_scan=True,
            can_status=True,
        )
        self.status_calls = 0
        self.scan_calls = 0

    def scan(self, *, cancel: CancellationToken | None = None):
        self.scan_calls += 1
        if cancel is not None:
            cancel.raise_if_cancelled()
        return (self.network,)

    def status(self, *, cancel: CancellationToken | None = None) -> WifiConnection:
        self.status_calls += 1
        return WifiConnection(
            network=self.network,
            state=WifiConnectionState.CONNECTED,
            interface=self.network.interface,
        )

    def connect(self, network: WifiNetwork, *, cancel: CancellationToken | None = None):
        raise AssertionError("setup must not connect to Wi-Fi")

    def disconnect(self, *, cancel: CancellationToken | None = None):
        raise AssertionError("setup must not disconnect from Wi-Fi")


class BlockingScanAdapter(SetupAdapter):
    """Adapter that keeps discovery active until the test releases it."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.scan_started = Event()
        self.scan_release = Event()

    def scan(self, *, cancel: CancellationToken | None = None):
        self.scan_started.set()
        while not self.scan_release.wait(0.01):
            if cancel is not None:
                cancel.raise_if_cancelled()
        return super().scan(cancel=cancel)


class BlockingStatusAdapter(SetupAdapter):
    """Adapter whose status call exits only after its cancellation token is set."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.status_started = False
        self.status_cancel: CancellationToken | None = None

    def status(self, *, cancel: CancellationToken | None = None) -> WifiConnection:
        self.status_started = True
        self.status_cancel = cancel
        assert cancel is not None
        while not cancel.is_cancelled:
            cancel.wait(0.01)
        raise WifiOperationCancelled("status cancelled")


def _network() -> WifiNetwork:
    return WifiNetwork(
        ssid="Guest network",
        bssid="aa:bb:cc:dd:ee:01",
        security=WifiSecurity.OPEN,
        signal_percent=80,
        interface="test0",
    )


@pytest.mark.asyncio
async def test_setup_scans_selects_and_requires_a_target() -> None:
    from portallens.tui.setup import PortalLensSetupApp, SetupNetworkItem

    adapter = SetupAdapter(_network())
    controller = WifiSessionController(adapter)
    app = PortalLensSetupApp(adapter, controller=controller)
    async with app.run_test(size=(120, 45)) as pilot:
        await pilot.pause()
        assert controller.state.phase is WifiPickerPhase.READY
        item = app.query_one("#networks").children[0]
        assert isinstance(item, SetupNetworkItem)
        app.on_list_view_selected(type("Event", (), {"item": item})())
        assert app.selected_network == adapter.network
        assert len(app.query_one("#networks").children) == 1
        app.query_one("#authorized").value = True
        app.query_one("#monitor").value = True
        await pilot.pause()
        app._start_investigation()
        await pilot.pause()
        assert "choose a Wi-Fi network" not in str(app.query_one("#status").render()).lower()
        assert "Read-only Wi-Fi monitoring" in str(app.query_one("#hero").render())
    assert app._started is True
    controller.close()


@pytest.mark.asyncio
async def test_setup_keyboard_selection_does_not_crash() -> None:
    from portallens.tui.setup import PortalLensSetupApp

    adapter = SetupAdapter(_network())
    controller = WifiSessionController(adapter)
    app = PortalLensSetupApp(adapter, controller=controller)
    async with app.run_test(size=(120, 45)) as pilot:
        await pilot.pause()
        networks = app.query_one("#networks")
        networks.focus()
        await pilot.press("down", "enter")
        await pilot.pause()
        assert app.is_running
        assert app.selected_network == adapter.network
        assert len(app.query_one("#networks").children) == 1
    controller.close()


@pytest.mark.asyncio
async def test_setup_controller_scan_disables_then_reenables_rows() -> None:
    from portallens.tui.setup import PortalLensSetupApp

    adapter = BlockingScanAdapter(_network())
    controller = WifiSessionController(adapter)
    app = PortalLensSetupApp(adapter, controller=controller, auto_scan=False)
    async with app.run_test(size=(120, 45)) as pilot:
        app.action_scan()
        for _ in range(100):
            if adapter.scan_started.is_set():
                break
            await pilot.pause(0.01)
        assert adapter.scan_started.is_set()
        await pilot.pause()
        assert app.query_one("#networks").disabled
        adapter.scan_release.set()
        await pilot.pause(0.1)
        assert controller.state.phase is WifiPickerPhase.READY
        assert not app.query_one("#networks").disabled
        assert len(app.query_one("#networks").children) == 1
    controller.close()


@pytest.mark.asyncio
async def test_setup_disables_stale_rows_during_scan() -> None:
    from portallens.tui.setup import PortalLensSetupApp

    network = _network()
    adapter = SetupAdapter(network)
    controller = WifiSessionController(
        adapter,
        initial_state=WifiPickerState(
            phase=WifiPickerPhase.READY,
            networks=(network,),
            generation=1,
        ),
    )
    app = PortalLensSetupApp(adapter, controller=controller, auto_scan=False)
    async with app.run_test(size=(120, 45)) as pilot:
        await pilot.pause()
        app._render_state(
            WifiPickerState(
                phase=WifiPickerPhase.SCANNING,
                networks=(network,),
                generation=2,
            )
        )
        assert app.query_one("#networks").disabled
        app._render_state(
            WifiPickerState(
                phase=WifiPickerPhase.READY,
                networks=(network,),
                generation=2,
            )
        )
        assert not app.query_one("#networks").disabled
    controller.close()


@pytest.mark.asyncio
async def test_setup_manual_rescan_does_not_overlap_active_scan() -> None:
    from portallens.tui.setup import PortalLensSetupApp

    adapter = BlockingScanAdapter(_network())
    controller = WifiSessionController(adapter)
    app = PortalLensSetupApp(adapter, controller=controller, auto_scan=False)
    async with app.run_test(size=(120, 45)) as pilot:
        app.action_scan()
        for _ in range(100):
            if adapter.scan_started.is_set():
                break
            await pilot.pause(0.01)
        assert adapter.scan_started.is_set()
        app.action_scan()
        assert adapter.scan_calls == 0
        adapter.scan_release.set()
        await pilot.pause()
        assert adapter.scan_calls == 1
    controller.close()


@pytest.mark.asyncio
async def test_setup_auto_refreshes_networks() -> None:
    from portallens.tui.setup import PortalLensSetupApp

    adapter = SetupAdapter(_network())
    controller = WifiSessionController(adapter)
    app = PortalLensSetupApp(adapter, controller=controller, refresh_interval=0.1)
    async with app.run_test(size=(120, 45)) as pilot:
        await pilot.pause(0.35)
        assert adapter.scan_calls >= 2
        assert len(app.query_one("#networks").children) == 1
    assert app._refresh_timer is None
    controller.close()


@pytest.mark.asyncio
async def test_setup_active_option_requires_authorization() -> None:
    from textual.widgets import Checkbox

    from portallens.tui.setup import PortalLensSetupApp

    adapter = SetupAdapter(_network())
    controller = WifiSessionController(adapter)
    app = PortalLensSetupApp(adapter, controller=controller, auto_scan=False)
    async with app.run_test(size=(120, 45)) as pilot:
        active = app.query_one("#active", Checkbox)
        active.value = True
        await pilot.pause()
        assert not app.query_one("#authorized", Checkbox).value
        assert "passive" in str(app.query_one("#status").render()).lower()
        assert not active.value
    controller.close()


@pytest.mark.asyncio
async def test_setup_requires_active_checks_for_url_monitoring() -> None:
    from portallens.tui.setup import PortalLensSetupApp

    adapter = SetupAdapter(_network())
    controller = WifiSessionController(adapter)
    app = PortalLensSetupApp(adapter, controller=controller, auto_scan=False)
    async with app.run_test(size=(120, 45)) as pilot:
        app.query_one("#portal-url").value = "https://portal.example/login"
        app.query_one("#authorized").value = True
        app.query_one("#monitor").value = True
        app._start_investigation()
        await pilot.pause()
        assert "enable active checks" in str(app.query_one("#status").render()).lower()
        assert not app._started
    controller.close()


@pytest.mark.asyncio
async def test_setup_cancels_status_worker_on_unmount() -> None:
    from portallens.tui.setup import PortalLensSetupApp

    adapter = BlockingStatusAdapter(_network())
    controller = WifiSessionController(adapter)
    app = PortalLensSetupApp(adapter, controller=controller, auto_scan=False)
    async with app.run_test(size=(120, 45)) as pilot:
        app._selected = adapter.network
        app.query_one("#monitor").value = True
        app._start_investigation()
        await pilot.pause()
        assert adapter.status_started
        app.on_unmount()
        await pilot.pause()
        assert adapter.status_cancel is not None
        assert adapter.status_cancel.is_cancelled
        assert app._status_timer is None
    controller.close()


@pytest.mark.asyncio
async def test_setup_rejects_invalid_portal_url() -> None:
    from portallens.tui.setup import PortalLensSetupApp

    adapter = SetupAdapter(_network())
    controller = WifiSessionController(adapter)
    app = PortalLensSetupApp(adapter, controller=controller, auto_scan=False)
    async with app.run_test(size=(120, 45)) as pilot:
        app.query_one("#portal-url").value = "not-a-url"
        app._start_investigation()
        await pilot.pause()
        assert "complete http:// or https://" in str(app.query_one("#status").render())
    controller.close()


def test_bare_command_opens_setup_and_starts_selected_url(monkeypatch) -> None:
    from portallens.tui.setup import SetupResult

    calls: list[SetupResult] = []
    monkeypatch.setattr(
        "portallens.cli._launch_primary_setup",
        lambda: SetupResult("http://portal.example/login", authorized=True, auto_run=True),
    )
    monkeypatch.setattr("portallens.cli._start_from_setup", calls.append)

    result = CliRunner().invoke(main, [])

    assert result.exit_code == 0, result.output
    assert calls == [SetupResult("http://portal.example/login", authorized=True, active=False, auto_run=True)]


def test_explicit_analyze_remains_scriptable() -> None:
    from tests.data import ISPMAN_URL, MAZ_URL

    result = CliRunner().invoke(main, ["analyze", ISPMAN_URL, MAZ_URL])

    assert result.exit_code == 0, result.output
    assert result.output.startswith("# PortalLens Report")


def test_no_wifi_adapter_still_allows_setup_launch(monkeypatch) -> None:
    from portallens.tui.setup import SetupResult
    from portallens.wifi import WifiAdapterUnavailable

    monkeypatch.setattr(
        "portallens.wifi.adapter_for_platform",
        lambda: (_ for _ in ()).throw(WifiAdapterUnavailable("no Wi-Fi device")),
    )
    result_holder: list[SetupResult | None] = []

    def run_setup(_self):
        result_holder.append(SetupResult("http://portal.example/login"))
        return result_holder[-1]

    monkeypatch.setattr("portallens.tui.PortalLensSetupApp.run", run_setup)
    monkeypatch.setattr("portallens.cli._start_from_setup", lambda _result: None)

    result = CliRunner().invoke(main, [])

    assert result.exit_code == 0, result.output
    assert result_holder == [SetupResult("http://portal.example/login")]
