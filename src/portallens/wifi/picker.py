"""Textual Wi-Fi network picker for read-only discovery sessions."""

from __future__ import annotations

from threading import get_ident
from typing import ClassVar

from rich.markup import escape
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.timer import Timer
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from portallens.wifi.adapter import WifiAdapter
from portallens.wifi.models import WifiNetwork
from portallens.wifi.session import WifiPickerPhase, WifiPickerState, WifiSessionController


class WifiNetworkItem(ListItem):
    """One selectable network row carrying its immutable domain object."""

    def __init__(self, network: WifiNetwork) -> None:
        self.network = network
        super().__init__(Label(self._label(network)))

    @staticmethod
    def _label(network: WifiNetwork) -> Text:
        signal = f"{network.signal_percent}%" if network.signal_percent is not None else "?"
        security = network.security.value.replace("_", " ")
        bssid = f"  {network.bssid}" if network.bssid else ""
        return Text.from_markup(
            f"[bold]{escape(network.display_name)}[/bold]  "
            f"[cyan]{escape(signal)}[/cyan]  [dim]{escape(security + bssid)}[/dim]"
        )


class WifiPickerApp(App[WifiNetwork | None]):
    """Discover and select a Wi-Fi network without connecting to it.

    ``r`` starts a new scan, ``c`` cancels the active scan, and Enter selects
    the highlighted row and exits with the selected :class:`WifiNetwork`.
    The app never calls ``connect`` and never accepts credentials.
    """

    TITLE = "PortalLens Wi-Fi Picker"
    SUB_TITLE = "read-only discovery"

    BINDINGS: ClassVar = [
        Binding("r", "rescan", "rescan"),
        Binding("c", "cancel_scan", "cancel scan"),
        Binding("q", "quit", "quit"),
    ]

    CSS = """
    Screen { layout: vertical; }
    #status { height: auto; padding: 1; border: round $primary; }
    #networks { height: 1fr; border: round $accent; }
    #hint { height: auto; padding: 1; color: $text-muted; }
    #selected { height: auto; padding: 1; border: round $success; }
    """

    def __init__(
        self,
        adapter: WifiAdapter,
        *,
        controller: WifiSessionController | None = None,
        auto_scan: bool = True,
        refresh_interval: float = 10.0,
    ) -> None:
        super().__init__()
        self._controller = controller or WifiSessionController(adapter)
        self._owns_controller = controller is None
        self._auto_scan = auto_scan
        self._refresh_interval = max(0.1, refresh_interval)
        self._latest_state = self._controller.state
        self._selected: WifiNetwork | None = None
        self._ui_thread_ident: int | None = None
        self._refresh_timer: Timer | None = None
        self._rendered_rows: tuple[tuple[object, ...], ...] = ()

    @property
    def controller(self) -> WifiSessionController:
        """Expose the controller for embedding and deterministic tests."""

        return self._controller

    @property
    def selected_network(self) -> WifiNetwork | None:
        """The network selected during this app session, if any."""

        return self._selected

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="status")
        with Vertical():
            yield ListView(id="networks")
            yield Static("No network selected", id="selected")
        yield Static("r rescan  ·  c cancel  ·  Enter select  ·  q quit", id="hint")
        yield Footer()

    def on_mount(self) -> None:
        self._ui_thread_ident = get_ident()
        self._controller.set_listener(self._receive_state)
        self._render_state(self._latest_state)
        if self._auto_scan:
            self.action_rescan()
            self._refresh_timer = self.set_interval(
                self._refresh_interval, lambda: self.action_rescan(automatic=True)
            )

    def action_rescan(self, *, automatic: bool = False) -> None:
        if self._controller.state.phase is WifiPickerPhase.SCANNING:
            if not automatic:
                self._render_error("a Wi-Fi scan is already in progress")
            return
        try:
            self._controller.scan()
        except RuntimeError as exc:
            self._render_error(str(exc))

    def action_cancel_scan(self) -> None:
        if not self._controller.cancel():
            self._render_error("no scan is currently running")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if not isinstance(item, WifiNetworkItem):
            return
        try:
            self._selected = self._controller.select(item.network.identity)
        except ValueError as exc:
            self._render_error(str(exc))
            return
        self.query_one("#selected", Static).update(
            f"Selected: {self._selected.display_name} — ready for the next authorized step"
        )
        self.exit(self._selected)

    def _receive_state(self, state: WifiPickerState) -> None:
        """Bridge worker-thread state delivery onto Textual's event loop."""

        if self._ui_thread_ident == get_ident():
            self._render_state(state)
        elif self.is_running:
            try:
                self.call_from_thread(self._render_state, state)
            except RuntimeError:
                # Textual may be shutting down between the lifecycle check
                # and dispatch; the controller remains usable for its owner.
                self._latest_state = state
        else:
            self._latest_state = state

    def _render_state(self, state: WifiPickerState) -> None:
        self._latest_state = state
        status = self.query_one("#status", Static)
        status.update(self._status_text(state))
        network_list = self.query_one("#networks", ListView)
        if state.phase is WifiPickerPhase.SCANNING:
            # Keep existing rows visible while the replacement scan runs;
            # Textual mounts ListItems asynchronously. The rows are stale
            # until the scan completes, so prevent selecting one.
            network_list.disabled = True
            return
        elif state.phase is WifiPickerPhase.READY:
            network_list.disabled = False
            desired_rows = _network_display_state(state)
            if desired_rows != self._rendered_rows:
                self._rendered_rows = desired_rows
                network_list.clear()
                for network in state.networks:
                    network_list.append(WifiNetworkItem(network))
        elif state.phase is WifiPickerPhase.FAILED:
            network_list.disabled = True
            self._render_error(state.error or "Wi-Fi scan failed")
        elif state.phase is WifiPickerPhase.CANCELLED:
            network_list.disabled = True

    def _render_error(self, message: str) -> None:
        self.query_one("#status", Static).update(f"Error: {message}")

    @staticmethod
    def _status_text(state: WifiPickerState) -> str:
        if state.phase is WifiPickerPhase.SCANNING:
            return f"Scanning for Wi-Fi networks… (generation {state.generation})"
        if state.phase is WifiPickerPhase.READY:
            return f"{len(state.networks)} network(s) found — choose one"
        if state.phase is WifiPickerPhase.CANCELLED:
            return "Scan cancelled — press r to scan again"
        if state.phase is WifiPickerPhase.FAILED:
            return f"Scan failed: {state.error or 'unknown error'}"
        return "Ready — press r to scan"

    def on_unmount(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
        self._controller.set_listener(None)
        if self._owns_controller:
            self._controller.close()


def _network_display_state(state: WifiPickerState) -> tuple[tuple[object, ...], ...]:
    """Return scan fields that can change what a rendered row displays."""

    return tuple(_network_display_item(network) for network in state.networks)


def _network_display_item(network: WifiNetwork) -> tuple[object, ...]:
    return (
        network.identity,
        network.display_name,
        network.security.value,
        network.signal_percent,
    )


__all__ = ["WifiNetworkItem", "WifiPickerApp"]
