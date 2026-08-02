"""Cross-platform Wi-Fi discovery and OS-mediated connection contracts.

The platform adapters in this package are read-only in this slice: they scan
and report host-reported status, while credentials and association operations
remain intentionally absent from the implementation boundary.
"""

from portallens.wifi.adapter import WifiAdapter, ensure_capability
from portallens.wifi.adapters import (
    LinuxWifiAdapter,
    MacOSWifiAdapter,
    WindowsWifiAdapter,
    adapter_for_platform,
    parse_airport_scan,
    parse_netsh_scan,
    parse_netsh_status,
    parse_networksetup_status,
    parse_nmcli_scan,
    parse_nmcli_status,
)
from portallens.wifi.command import CommandResult, CommandRunner, SubprocessCommandRunner
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
    "CommandResult",
    "CommandRunner",
    "LinuxWifiAdapter",
    "MacOSWifiAdapter",
    "SubprocessCommandRunner",
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
    "WindowsWifiAdapter",
    "adapter_for_platform",
    "ensure_capability",
    "parse_airport_scan",
    "parse_netsh_scan",
    "parse_netsh_status",
    "parse_networksetup_status",
    "parse_nmcli_scan",
    "parse_nmcli_status",
]
