"""Thread-safe Wi-Fi picker state and scan orchestration.

This module deliberately stops at discovery and selection. It never accepts
credentials, associates with an access point, launches a browser, or invokes
portal/bypass logic. Platform adapters remain responsible for host commands;
the controller only coordinates their read-only ``scan`` operation.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from threading import Lock

from portallens.wifi.adapter import WifiAdapter
from portallens.wifi.errors import WifiOperationCancelled
from portallens.wifi.models import CancellationToken, WifiNetwork


class WifiPickerPhase(str, Enum):
    """Lifecycle phase shown by the network picker."""

    IDLE = "idle"
    SCANNING = "scanning"
    READY = "ready"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class WifiPickerState:
    """Immutable picker snapshot delivered to the presentation layer."""

    phase: WifiPickerPhase = WifiPickerPhase.IDLE
    networks: tuple[WifiNetwork, ...] = ()
    selected_identity: tuple[str | None, str | None, str | None] | None = None
    generation: int = 0
    error: str | None = None

    @property
    def selected_network(self) -> WifiNetwork | None:
        """Return the selected network still present in this snapshot."""

        if self.selected_identity is None:
            return None
        return next(
            (network for network in self.networks if network.identity == self.selected_identity),
            None,
        )


StateListener = Callable[[WifiPickerState], None]


class WifiSessionController:
    """Coordinate cancellable, single-flight Wi-Fi discovery.

    Every scan receives a monotonically increasing generation. Completion
    callbacks may arrive after a cancellation or a newer scan; only the
    callback whose generation is still current can publish results. This
    makes rapid rescan/cancel interactions deterministic and prevents stale
    networks from replacing a newer picker snapshot.
    """

    def __init__(
        self,
        adapter: WifiAdapter,
        *,
        on_state: StateListener | None = None,
        executor: ThreadPoolExecutor | None = None,
        initial_state: WifiPickerState | None = None,
    ) -> None:
        self._adapter = adapter
        self._on_state = on_state
        self._executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="portallens-wifi")
        self._owns_executor = executor is None
        self._lock = Lock()
        self._state = initial_state or WifiPickerState()
        self._generation = self._state.generation
        self._cancel: CancellationToken | None = None
        self._closed = False

    @property
    def state(self) -> WifiPickerState:
        """Return the latest immutable state snapshot."""

        with self._lock:
            return self._state

    def scan(self) -> int:
        """Start a new scan and return its generation number.

        A newer scan supersedes an older one. The old adapter call receives a
        cancellation request, and any late result is discarded by generation
        checks in ``_complete``.
        """

        with self._lock:
            self._ensure_open()
            if self._cancel is not None:
                self._cancel.cancel()
            self._generation += 1
            generation = self._generation
            token = CancellationToken()
            self._cancel = token
            previous = self._state
            state = WifiPickerState(
                phase=WifiPickerPhase.SCANNING,
                networks=previous.networks,
                selected_identity=previous.selected_identity,
                generation=generation,
            )
            self._state = state
        self._publish(state)
        future: Future[tuple[WifiNetwork, ...]] = self._executor.submit(self._run_scan, token)
        with self._lock:
            if self._closed or generation != self._generation:
                token.cancel()
        future.add_done_callback(lambda completed: self._complete(generation, token, completed))
        return generation

    def cancel(self) -> bool:
        """Cancel the current scan, preserving the last visible networks."""

        with self._lock:
            if self._closed or self._state.phase is not WifiPickerPhase.SCANNING:
                return False
            if self._cancel is not None:
                self._cancel.cancel()
            self._generation += 1
            current = self._state
            state = WifiPickerState(
                phase=WifiPickerPhase.CANCELLED,
                networks=current.networks,
                selected_identity=current.selected_identity,
                generation=self._generation,
            )
            self._state = state
        self._publish(state)
        return True

    def set_listener(self, listener: StateListener | None) -> None:
        """Replace the presentation listener used for future state updates."""

        with self._lock:
            self._on_state = listener

    def select(self, identity: tuple[str | None, str | None, str | None]) -> WifiNetwork:
        """Select one discovered network without connecting to it.

        Selection is validated against the current snapshot so a stale UI row
        cannot select a network that disappeared during a rescan.
        """

        with self._lock:
            if self._state.phase is not WifiPickerPhase.READY:
                raise ValueError("network selection requires a ready scan")
            network = next(
                (item for item in self._state.networks if item.identity == identity),
                None,
            )
            if network is None:
                raise ValueError("network is not present in the current scan")
            state = WifiPickerState(
                phase=self._state.phase,
                networks=self._state.networks,
                selected_identity=identity,
                generation=self._state.generation,
                error=self._state.error,
            )
            self._state = state
        self._publish(state)
        return network

    def close(self) -> None:
        """Cancel outstanding work and release the controller's executor."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._cancel is not None:
                self._cancel.cancel()
            self._generation += 1
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def __enter__(self) -> WifiSessionController:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _run_scan(self, token: CancellationToken) -> tuple[WifiNetwork, ...]:
        """Run the adapter's read-only scan in the worker thread."""

        token.raise_if_cancelled()
        return tuple(self._adapter.scan(cancel=token))

    def _complete(
        self,
        generation: int,
        token: CancellationToken,
        future: Future[tuple[WifiNetwork, ...]],
    ) -> None:
        try:
            networks = future.result()
        except WifiOperationCancelled:
            with self._lock:
                if generation != self._generation or self._closed:
                    return
                current = self._state
                state = WifiPickerState(
                    phase=WifiPickerPhase.CANCELLED,
                    networks=current.networks,
                    selected_identity=current.selected_identity,
                    generation=generation,
                )
                self._state = state
            self._publish(state)
            return
        except Exception as exc:
            with self._lock:
                if generation != self._generation or self._closed:
                    return
                current = self._state
                state = WifiPickerState(
                    phase=WifiPickerPhase.FAILED,
                    networks=current.networks,
                    selected_identity=current.selected_identity,
                    generation=generation,
                    error=str(exc),
                )
                self._state = state
            self._publish(state)
            return

        with self._lock:
            if self._closed or generation != self._generation or token.is_cancelled:
                return
            current = self._state
            identities = {network.identity for network in networks}
            selected = current.selected_identity if current.selected_identity in identities else None
            state = WifiPickerState(
                phase=WifiPickerPhase.READY,
                networks=networks,
                selected_identity=selected,
                generation=generation,
            )
            self._state = state
        self._publish(state)

    def _publish(self, state: WifiPickerState) -> None:
        if self._on_state is not None:
            self._on_state(state)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Wi-Fi session controller is closed")

__all__ = ["WifiPickerPhase", "WifiPickerState", "WifiSessionController"]
