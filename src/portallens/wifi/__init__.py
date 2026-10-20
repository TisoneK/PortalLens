"""Cross-platform Wi-Fi discovery and OS-mediated connection contracts.

The platform adapters and session controller in this package are read-only in
this slice: they scan, report host status, and coordinate selection, while
credentials, association, packet operations, browser launch, and bypass
operations remain outside the implementation boundary. The Textual picker is
available from :mod:`portallens.wifi.picker` and is intentionally not imported
here so core imports stay dependency-free.

The :mod:`portallens.wifi.watch` connectivity watch accumulates the bounded
probe outcomes from :mod:`portallens.wifi.captive_portal` over time and
connection epochs so a report can flag access that continues (or returns)
after a recorded package expiry. It introduces no network behavior of its
own.
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
from portallens.wifi.captive_portal import (
    ANDROID_CLIENTS3_GENERATE_204,
    ANDROID_GENERATE_204,
    APPLE_HOTSPOT,
    FIREFOX_CANONICAL,
    GNOME_NETWORK_STATUS,
    PROBE_PROFILES,
    WINDOWS_CONNECT_TEST,
    WINDOWS_NCSI,
    CaptivePortalDetector,
    CaptivePortalMetadata,
    CaptivePortalProbeProfile,
    CaptivePortalProbeResult,
    CaptivePortalResponse,
    WifiProbePlatform,
    analyze_probe_result,
    apply_probe_result,
    parse_captive_portal_metadata,
    profiles_for_platform,
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
    safe_portal_url,
)
from portallens.wifi.session import WifiPickerPhase, WifiPickerState, WifiSessionController
from portallens.wifi.watch import (
    JOURNAL_VERSION,
    AccessWatchReport,
    ConnectivityWatch,
    WatchBoundary,
    WatchBoundaryKind,
    WatchSample,
    WatchSampleState,
    WatchTransition,
    default_watch_journal_path,
    load_watch_journal,
    save_watch_journal,
)

__all__ = [
    "ANDROID_CLIENTS3_GENERATE_204",
    "ANDROID_GENERATE_204",
    "APPLE_HOTSPOT",
    "FIREFOX_CANONICAL",
    "GNOME_NETWORK_STATUS",
    "JOURNAL_VERSION",
    "PROBE_PROFILES",
    "WINDOWS_CONNECT_TEST",
    "WINDOWS_NCSI",
    "AccessWatchReport",
    "CancellationToken",
    "CaptivePortalDetector",
    "CaptivePortalMetadata",
    "CaptivePortalProbeProfile",
    "CaptivePortalProbeResult",
    "CaptivePortalResponse",
    "CommandResult",
    "CommandRunner",
    "ConnectivityWatch",
    "LinuxWifiAdapter",
    "MacOSWifiAdapter",
    "SubprocessCommandRunner",
    "WatchBoundary",
    "WatchBoundaryKind",
    "WatchSample",
    "WatchSampleState",
    "WatchTransition",
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
    "WifiPickerPhase",
    "WifiPickerState",
    "WifiProbePlatform",
    "WifiSecurity",
    "WifiSessionController",
    "WifiUnsupportedOperation",
    "WindowsWifiAdapter",
    "adapter_for_platform",
    "analyze_probe_result",
    "apply_probe_result",
    "default_watch_journal_path",
    "ensure_capability",
    "load_watch_journal",
    "parse_airport_scan",
    "parse_captive_portal_metadata",
    "parse_netsh_scan",
    "parse_netsh_status",
    "parse_networksetup_status",
    "parse_nmcli_scan",
    "parse_nmcli_status",
    "profiles_for_platform",
    "safe_portal_url",
    "save_watch_journal",
]
