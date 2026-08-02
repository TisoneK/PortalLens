"""Primary PortalLens setup screen.

The setup screen is the friendly front door for ``portallens``. It keeps the
advanced controls visible, but makes the safe defaults obvious: discovery is
read-only, active work requires an explicit authorization checkbox, and the
host operating system remains responsible for Wi-Fi association.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from threading import get_ident
from typing import ClassVar
from urllib.parse import urlsplit

from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from portallens.wifi.adapter import WifiAdapter
from portallens.wifi.errors import WifiAdapterUnavailable, WifiOperationCancelled
from portallens.wifi.models import (
    CancellationToken,
    WifiAdapterCapabilities,
    WifiConnection,
    WifiNetwork,
)
from portallens.wifi.session import WifiPickerPhase, WifiPickerState, WifiSessionController


@dataclass(frozen=True)
class SetupResult:
    """Configuration returned when the user starts a portal-URL session."""

    target_url: str
    authorized: bool = False
    active: bool = False
    auto_run: bool = False
    monitor: bool = False


class SetupUnavailableAdapter:
    """Adapter shown when the host has no usable Wi-Fi service.

    The URL setup path must remain available even on a server or desktop
    without Wi-Fi hardware. Scanning reports the original availability error;
    no fake network is shown and no operation is attempted.
    """

    def __init__(self, message: str) -> None:
        self._message = message
        self.capabilities = WifiAdapterCapabilities(
            platform="unavailable",
            adapter_name="none",
            can_scan=False,
            can_status=False,
            notes=("Wi-Fi unavailable; portal URL setup remains available",),
        )

    def scan(self, *, cancel: CancellationToken | None = None) -> tuple[WifiNetwork, ...]:
        del cancel
        raise WifiAdapterUnavailable(self._message)

    def status(self, *, cancel: CancellationToken | None = None) -> WifiConnection:
        del cancel
        raise WifiAdapterUnavailable(self._message)

    def connect(self, network: WifiNetwork, *, cancel: CancellationToken | None = None) -> WifiConnection:
        del network, cancel
        raise WifiAdapterUnavailable(self._message)

    def disconnect(self, *, cancel: CancellationToken | None = None) -> WifiConnection:
        del cancel
        raise WifiAdapterUnavailable(self._message)


class SetupNetworkItem(ListItem):
    """A Wi-Fi network row in the primary setup screen."""

    def __init__(self, network: WifiNetwork) -> None:
        self.network = network
        signal = f"{network.signal_percent}%" if network.signal_percent is not None else "?"
        security = network.security.value.replace("_", " ")
        super().__init__(Label(f"{network.display_name}  ·  {signal}  ·  {security}"))


class PortalLensSetupApp(App[SetupResult | None]):
    """The main setup experience launched by bare ``portallens``.

    A typed portal URL starts the existing live investigation console. A
    selected Wi-Fi network starts a clearly labelled read-only host-status
    monitor in this setup screen; association, portal detection, and
    credentials remain outside the current desktop-adapter boundary.
    """

    TITLE = "PortalLens"
    SUB_TITLE = "set up an investigation"

    BINDINGS: ClassVar = [
        Binding("q", "quit", "quit"),
        Binding("r", "scan", "scan Wi-Fi"),
    ]

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }
    #hero {
        height: auto;
        padding: 1 2;
        background: $boost;
        border: round $primary;
    }
    #columns {
        height: 1fr;
        padding: 1;
    }
    #setup-panel, #target-panel {
        width: 1fr;
        padding: 1 2;
        border: round $accent;
    }
    #target-panel {
        margin-left: 1;
    }
    #target-panel-title, #setup-panel-title {
        text-style: bold;
        color: $primary;
        padding-bottom: 1;
    }
    #portal-url {
        margin: 1 0;
    }
    #networks {
        height: 1fr;
        margin: 1 0;
        border: round $secondary;
    }
    #selection, #status {
        height: auto;
        padding: 1;
        margin-top: 1;
        background: $boost;
    }
    #activity {
        height: 8;
        margin: 0 2 1 2;
        border: round $secondary;
    }
    .option {
        height: auto;
        margin: 1 0;
    }
    Button {
        margin: 1 1 0 0;
    }
    #start {
        background: $success;
    }
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
        self._adapter = adapter
        self._controller = controller or WifiSessionController(adapter)
        self._owns_controller = controller is None
        self._auto_scan = auto_scan
        self._refresh_interval = max(0.1, refresh_interval)
        self._latest_state = self._controller.state
        self._selected: WifiNetwork | None = None
        self._ui_thread_ident: int | None = None
        self._started = False
        self._status_timer: Timer | None = None
        self._refresh_timer: Timer | None = None
        self._status_cancel: CancellationToken | None = None
        self._rendered_rows: tuple[tuple[object, ...], ...] = ()

    @property
    def controller(self) -> WifiSessionController:
        """Expose the discovery controller for embedding and tests."""

        return self._controller

    @property
    def selected_network(self) -> WifiNetwork | None:
        """Return the selected network, if one was chosen."""

        return self._selected

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(
            "[bold]Set up an investigation[/bold]\n"
            "Choose a portal URL or select a nearby Wi-Fi network. "
            "You can review options before starting.",
            id="hero",
        )

        with Horizontal(id="columns"):
            with Vertical(id="setup-panel"):
                yield Static("INVESTIGATION OPTIONS", id="setup-panel-title")
                yield Checkbox(
                    "I have permission to assess this target",
                    id="authorized",
                    classes="option",
                )
                yield Checkbox(
                    "Enable active checks",
                    id="active",
                    classes="option",
                )
                yield Checkbox(
                    "Automatically run recommended steps",
                    id="auto",
                    classes="option",
                )
                yield Checkbox(
                    "Enable continuous monitoring",
                    id="monitor",
                    classes="option",
                )
                yield Static(
                    "For a URL, continuous monitoring runs authorized checks. "
                    "For Wi-Fi, it only reads status reported by the computer.",
                    id="status",
                )
            with Vertical(id="target-panel"):
                yield Static("CHOOSE A TARGET", id="target-panel-title")
                yield Input(
                    placeholder="Optional: paste a captive-portal URL",
                    id="portal-url",
                )
                yield Button("Scan nearby Wi-Fi", id="scan", variant="default")
                yield ListView(id="networks")
                yield Static("No Wi-Fi network selected", id="selection")
        yield RichLog(id="activity", wrap=True)
        with Horizontal(id="actions"):
            yield Button("Start investigation", id="start", variant="success")
            yield Button("Quit", id="quit", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        self._ui_thread_ident = get_ident()
        self._controller.set_listener(self._receive_state)
        self._render_state(self._latest_state)
        self._feed("Choose a URL or scan and select a Wi-Fi network.")
        if self._auto_scan:
            self.action_scan()
            self._refresh_timer = self.set_interval(self._refresh_interval, self._refresh_scan)

    def _refresh_scan(self) -> None:
        """Refresh discovery without interrupting read-only monitoring."""

        self.action_scan(automatic=True)

    def action_scan(self, *, automatic: bool = False) -> None:
        if self._controller.state.phase is WifiPickerPhase.SCANNING:
            if not automatic:
                self._feed("A Wi-Fi scan is already in progress.")
            return
        if self._started and not automatic:
            self._feed("Stop the current session before scanning again.")
            return
        try:
            generation = self._controller.scan()
        except RuntimeError as exc:
            self._set_status(str(exc), error=True)
            return
        self._feed(f"Scanning nearby Wi-Fi networks (generation {generation}) …")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scan":
            self.action_scan()
        elif event.button.id == "start":
            self._start_investigation()
        elif event.button.id == "quit":
            self.exit()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "active":
            if event.value and not self.query_one("#authorized", Checkbox).value:
                event.checkbox.value = False
                self._set_status("Active portal checks require the authorization option.", error=True)
            elif not event.value:
                self._set_status("Passive mode selected — no active checks will run.")
        elif event.checkbox.id == "authorized" and not event.value:
            active = self.query_one("#active", Checkbox)
            if active.value:
                active.value = False
            self._set_status("Passive mode selected — no active checks will run.")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, SetupNetworkItem):
            return
        try:
            self._selected = self._controller.select(event.item.network.identity)
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return
        self.query_one("#selection", Static).update(
            f"Selected: [bold]{escape(self._selected.display_name)}[/bold]  "
            "· ready to start"
        )
        self._feed(f"Target selected: {escape(self._selected.display_name)}")

    def _start_investigation(self) -> None:
        if self._started:
            self._stop_session()
            return
        authorized = self.query_one("#authorized", Checkbox).value
        active = self.query_one("#active", Checkbox).value
        if active and not authorized:
            self._set_status("Confirm authorization before enabling active checks.", error=True)
            return
        url = self.query_one("#portal-url", Input).value.strip()
        if url:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                self._set_status("Enter a complete http:// or https:// portal URL.", error=True)
                return
            monitor = self.query_one("#monitor", Checkbox).value
            if monitor and not active:
                self._set_status("Enable active checks before starting URL monitoring.", error=True)
                return
            if monitor and not authorized:
                self._set_status("URL monitoring requires the authorization option.", error=True)
                return
            self.exit(
                SetupResult(
                    target_url=url,
                    authorized=authorized,
                    active=active,
                    auto_run=self.query_one("#auto", Checkbox).value,
                    monitor=monitor,
                )
            )
            return
        if self._selected is None:
            self._set_status("Choose a Wi-Fi network or enter a portal URL first.", error=True)
            return
        if not self.query_one("#monitor", Checkbox).value:
            self._set_status(
                "For a Wi-Fi target, enable 'Enable continuous monitoring' or enter a portal URL.",
                error=True,
            )
            return
        self._started = True
        self.query_one("#hero", Static).update(
            "[bold]Read-only Wi-Fi monitoring[/bold]\n"
            "PortalLens is displaying host status; it will not change the connection."
        )
        self.query_one("#start", Button).label = "Stop monitoring"
        self._set_status(
            f"Read-only monitoring: {self._selected.display_name}. "
            "PortalLens will not change the host connection.",
        )
        self._feed(
            "Read-only Wi-Fi monitoring started — waiting for the operating "
            "system to report the selected network."
        )
        self._status_timer = self.set_interval(3.0, self._poll_status)
        self._poll_status()

    def _poll_status(self) -> None:
        if not self._started or self._status_cancel is not None:
            return
        self._status_cancel = CancellationToken()
        self._status_worker(self._status_cancel)

    @work(thread=True, exclusive=True)
    def _status_worker(self, cancel: CancellationToken) -> None:
        try:
            try:
                connection = self._adapter.status(cancel=cancel)
            except WifiOperationCancelled:
                return
            except Exception as exc:
                with suppress(RuntimeError):
                    self.call_from_thread(self._show_status_error, str(exc))
                return
            # Textual may begin unmounting while an OS status command is
            # returning; the session is already shutting down in that case.
            if not cancel.is_cancelled:
                with suppress(RuntimeError):
                    self.call_from_thread(self._show_connection, connection)
        finally:
            with suppress(RuntimeError):
                self.call_from_thread(self._finish_status_worker, cancel)

    def _finish_status_worker(self, cancel: CancellationToken) -> None:
        if self._status_cancel is cancel:
            self._status_cancel = None

    def _show_connection(self, connection: WifiConnection) -> None:
        state = connection.state.value.replace("_", " ")
        current = connection.network.display_name
        self._set_status(f"Live status: {state} · host reports {current}")
        self._feed(f"Host status: {state} · {escape(current)}")

    def _show_status_error(self, message: str) -> None:
        self._set_status(f"Status unavailable: {message}", error=True)

    def _stop_session(self) -> None:
        self._started = False
        if self._status_cancel is not None:
            self._status_cancel.cancel()
            self._status_cancel = None
        if self._status_timer is not None:
            self._status_timer.stop()
            self._status_timer = None
        self.query_one("#hero", Static).update(
            "[bold]Set up an investigation[/bold]\n"
            "Choose a portal URL or select a nearby Wi-Fi network. You can review options before starting."
        )
        self.query_one("#start", Button).label = "Start investigation"
        self._set_status("Wi-Fi monitoring stopped.")
        self._feed("Session stopped.")

    def _receive_state(self, state: WifiPickerState) -> None:
        if self._ui_thread_ident == get_ident():
            self._render_state(state)
        elif self.is_running:
            with suppress(RuntimeError):
                self.call_from_thread(self._render_state, state)
        else:
            self._latest_state = state

    def _render_state(self, state: WifiPickerState) -> None:
        self._latest_state = state
        networks = self.query_one("#networks", ListView)
        if state.phase is WifiPickerPhase.SCANNING:
            # Keep the previous rows visible while the replacement scan runs;
            # Textual mounts ListItems asynchronously, so clearing here can
            # race with a pending mount and leave the list empty. The rows are
            # stale until the scan completes, so prevent selecting one.
            networks.disabled = True
            self._set_status("Scanning nearby Wi-Fi networks …")
        elif state.phase is WifiPickerPhase.READY:
            networks.disabled = False
            desired_rows = _network_display_state(state)
            if desired_rows != self._rendered_rows:
                self._rendered_rows = desired_rows
                networks.clear()
                for network in state.networks:
                    networks.append(SetupNetworkItem(network))
            self._set_status(f"{len(state.networks)} network(s) found — choose one")
        elif state.phase is WifiPickerPhase.FAILED:
            networks.disabled = True
            self._set_status(state.error or "Wi-Fi scan failed", error=True)
        elif state.phase is WifiPickerPhase.CANCELLED:
            networks.disabled = True
            self._set_status("Scan cancelled — press r or Scan nearby Wi-Fi to try again")

    def _set_status(self, message: str, *, error: bool = False) -> None:
        if not self.is_running:
            return
        prefix = "Error: " if error else ""
        self.query_one("#status", Static).update(prefix + message)

    def _feed(self, message: str) -> None:
        if self.is_running:
            self.query_one(RichLog).write(message)

    async def action_quit(self) -> None:
        self.exit()

    def on_unmount(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
        if self._status_timer is not None:
            self._status_timer.stop()
            self._status_timer = None
        if self._status_cancel is not None:
            self._status_cancel.cancel()
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


__all__ = ["PortalLensSetupApp", "SetupNetworkItem", "SetupResult", "SetupUnavailableAdapter"]
