"""Cross-platform Wi-Fi discovery and OS-mediated connection contracts.

This package contains no platform subprocesses yet. It defines the stable,
hardware-independent core that Windows, macOS, and Linux adapters will
implement in later slices. Credentials and packet-level operations are
intentionally absent from the API.
"""

from portallens.wifi.adapter import WifiAdapter, ensure_capability
from portallens.wifi.errors import (
    WifiAdapterUnavailable,
    WifiConnectionError,
    WifiError,
    WifiOperationCancelled,
    WifiOperationTimeout,
    WifiPermissionError,
    WifiUnsupportedOperation,
)
from portallens.wifi.models import (
    CancellationToken,
    WifiAdapterCapabilities,
    WifiConnection,
    WifiConnectionState,
    WifiNetwork,
    WifiSecurity,
)

__all__ = [
    "CancellationToken",
    "WifiAdapter",
    "WifiAdapterCapabilities",
    "WifiAdapterUnavailable",
    "WifiConnection",
    "WifiConnectionError",
    "WifiConnectionState",
    "WifiError",
    "WifiNetwork",
    "WifiOperationCancelled",
    "WifiOperationTimeout",
    "WifiPermissionError",
    "WifiSecurity",
    "WifiUnsupportedOperation",
    "ensure_capability",
]
