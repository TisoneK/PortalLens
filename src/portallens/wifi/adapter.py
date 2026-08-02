"""Platform-neutral contract for OS-mediated Wi-Fi operations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from portallens.wifi.models import (
    CancellationToken,
    WifiAdapterCapabilities,
    WifiConnection,
    WifiNetwork,
)


@runtime_checkable
class WifiAdapter(Protocol):
    """A desktop platform adapter backed by the host operating system.

    Implementations must delegate association and authentication to the OS.
    The contract deliberately accepts a selected :class:`WifiNetwork`, not a
    password or credential mapping. Every potentially blocking operation gets
    a cancellation token that the implementation must poll between system
    calls and before returning.
    """

    @property
    def capabilities(self) -> WifiAdapterCapabilities:
        """Describe supported operations and platform limitations."""
        ...

    def scan(self, *, cancel: CancellationToken | None = None) -> Sequence[WifiNetwork]:
        """Return the currently visible networks."""
        ...

    def connect(
        self,
        network: WifiNetwork,
        *,
        cancel: CancellationToken | None = None,
    ) -> WifiConnection:
        """Ask the host OS to connect to an already selected network."""
        ...

    def status(self, *, cancel: CancellationToken | None = None) -> WifiConnection:
        """Return the current host-reported connection state."""
        ...

    def disconnect(self, *, cancel: CancellationToken | None = None) -> WifiConnection:
        """Ask the host OS to disconnect from the current network."""
        ...


def ensure_capability(adapter: WifiAdapter, operation: str) -> None:
    """Raise a clear error when an adapter cannot provide an operation."""

    from portallens.wifi.errors import WifiUnsupportedOperation

    attribute = f"can_{operation}"
    if not getattr(adapter.capabilities, attribute, False):
        raise WifiUnsupportedOperation(
            f"Wi-Fi adapter {adapter.capabilities.adapter_name!r} does not support {operation}"
        )


__all__ = ["WifiAdapter", "ensure_capability"]
