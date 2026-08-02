"""Tests for the read-only Wi-Fi picker/session slice."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event

import pytest

from portallens.wifi import (
    CancellationToken,
    WifiAdapterCapabilities,
    WifiNetwork,
    WifiSecurity,
)
from portallens.wifi.session import WifiPickerPhase, WifiPickerState, WifiSessionController


@dataclass
class FakeAdapter:
    results: tuple[tuple[WifiNetwork, ...], ...]
    block_first: bool = False

    def __post_init__(self) -> None:
        self.calls = 0
        self.started = Event()
        self.release = Event()
        self.tokens: list[CancellationToken | None] = []
        self.capabilities = WifiAdapterCapabilities(platform="test", adapter_name="fixture")

    def scan(self, *, cancel=None):
        index = self.calls
        self.calls += 1
        self.tokens.append(cancel)
        self.started.set()
        if index == 0 and self.block_first:
            while not self.release.wait(0.01):
                if cancel is not None:
                    cancel.raise_if_cancelled()
        if cancel is not None:
            cancel.raise_if_cancelled()
        return self.results[min(index, len(self.results) - 1)]

    def connect(self, network, *, cancel=None):
        raise AssertionError("picker must not connect")

    def status(self, *, cancel=None):
        raise AssertionError("picker does not need status")

    def disconnect(self, *, cancel=None):
        raise AssertionError("picker must not disconnect")


def _net(name: str, bssid: str) -> WifiNetwork:
    return WifiNetwork(
        ssid=name,
        bssid=bssid,
        security=WifiSecurity.OPEN,
        signal_percent=70,
        interface="test0",
    )


class TestWifiSessionController:
    def test_scan_publishes_ready_state_and_selection(self) -> None:
        network = _net("Guest", "aa:bb:cc:dd:ee:01")
        states = []
        adapter = FakeAdapter(((network,),))
        with WifiSessionController(adapter, on_state=states.append) as controller:
            generation = controller.scan()
            assert adapter.started.wait(1)
            assert _wait_for(lambda: controller.state.phase is WifiPickerPhase.READY)
            assert controller.state.generation == generation
            assert controller.state.networks == (network,)
            selected = controller.select(network.identity)
            assert selected == network
            assert controller.state.selected_network == network
        assert states[0].phase is WifiPickerPhase.SCANNING
        assert states[-1].selected_network == network

    def test_cancellation_stops_scan_and_preserves_previous_networks(self) -> None:
        old = _net("Old", "aa:bb:cc:dd:ee:01")
        adapter = FakeAdapter(((old,),), block_first=True)
        initial = WifiPickerState(phase=WifiPickerPhase.READY, networks=(old,))
        with WifiSessionController(adapter, initial_state=initial) as controller:
            controller.scan()
            assert adapter.started.wait(1)
            assert controller.cancel() is True
            assert controller.state.phase is WifiPickerPhase.CANCELLED
            assert controller.state.networks == (old,)
            assert controller.cancel() is False

    def test_stale_scan_result_cannot_replace_newer_generation(self) -> None:
        first = _net("First", "aa:bb:cc:dd:ee:01")
        second = _net("Second", "aa:bb:cc:dd:ee:02")
        adapter = FakeAdapter(((first,), (second,)), block_first=True)
        executor = ThreadPoolExecutor(max_workers=2)
        with WifiSessionController(adapter, executor=executor) as controller:
            first_generation = controller.scan()
            assert adapter.started.wait(1)
            second_generation = controller.scan()
            assert second_generation > first_generation
            assert _wait_for(lambda: controller.state.phase is WifiPickerPhase.READY)
            assert controller.state.generation == second_generation
            assert controller.state.networks == (second,)
            adapter.release.set()
            assert _wait_for(lambda: adapter.calls >= 2)
            assert controller.state.networks == (second,)
        executor.shutdown(wait=True)

    def test_selection_rejects_stale_identity(self) -> None:
        adapter = FakeAdapter(((),))
        with WifiSessionController(adapter) as controller, pytest.raises(ValueError, match="ready scan"):
            controller.select(("test0", "Missing", None))

    def test_selection_is_rejected_while_rescanning(self) -> None:
        network = _net("Guest", "aa:bb:cc:dd:ee:03")
        adapter = FakeAdapter(((network,),), block_first=True)
        initial = WifiPickerState(
            phase=WifiPickerPhase.SCANNING,
            networks=(network,),
            generation=1,
        )
        with WifiSessionController(adapter, initial_state=initial) as controller, pytest.raises(
            ValueError, match="ready scan"
        ):
            controller.select(network.identity)

    def test_closed_controller_rejects_new_scan(self) -> None:
        adapter = FakeAdapter(((),))
        controller = WifiSessionController(adapter)
        controller.close()
        with pytest.raises(RuntimeError, match="closed"):
            controller.scan()


@pytest.mark.asyncio
async def test_picker_renders_networks_and_selects_without_connecting() -> None:
    from portallens.wifi.picker import WifiNetworkItem, WifiPickerApp

    network = _net("Guest", "aa:bb:cc:dd:ee:10")
    adapter = FakeAdapter(((network,),))
    controller = WifiSessionController(adapter)
    app = WifiPickerApp(adapter, controller=controller, auto_scan=False)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_rescan()
        await pilot.pause()
        assert _wait_for(lambda: controller.state.phase is WifiPickerPhase.READY)
        await pilot.pause()
        item = app.query_one("#networks").children[0]
        assert isinstance(item, WifiNetworkItem)
        app.query_one("#networks").index = 0
        app.on_list_view_selected(type("Event", (), {"item": item})())
        await pilot.pause()
    assert app.selected_network == network
    controller.close()


def _wait_for(predicate, timeout: float = 1.0) -> bool:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()
