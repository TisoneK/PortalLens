"""Immutable, credential-free value objects for live Wi-Fi investigations.

The models in this module intentionally describe what the host OS reports;
they do not contain passwords, tokens, packet data, or credential mappings.
Platform adapters can serialize these allow-listed fields for future
investigation events without accidentally persisting secrets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Event
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from portallens.wifi.errors import WifiOperationCancelled


class WifiSecurity(str, Enum):
    """Normalized security classification reported by a Wi-Fi adapter."""

    OPEN = "open"
    WEP = "wep"
    WPA_PERSONAL = "wpa_personal"
    WPA_ENTERPRISE = "wpa_enterprise"
    UNKNOWN = "unknown"


class WifiConnectionState(str, Enum):
    """Lifecycle states a host-mediated connection may report."""

    DISCONNECTED = "disconnected"
    SCANNING = "scanning"
    ASSOCIATING = "associating"
    CONNECTED = "connected"
    IP_CONFIGURED = "ip_configured"
    CAPTIVE_PORTAL = "captive_portal"
    ONLINE = "online"
    DISCONNECTING = "disconnecting"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class WifiAdapterCapabilities:
    """Operations a concrete platform adapter can safely provide."""

    platform: str
    adapter_name: str
    can_scan: bool = True
    can_connect: bool = False
    can_disconnect: bool = False
    can_status: bool = True
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the explicit, persistence-safe capability representation."""

        return {
            "platform": self.platform,
            "adapter_name": self.adapter_name,
            "can_scan": self.can_scan,
            "can_connect": self.can_connect,
            "can_disconnect": self.can_disconnect,
            "can_status": self.can_status,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class WifiNetwork:
    """A discovered access point as reported by the host OS.

    ``ssid`` may be ``None`` for a hidden network. ``bssid`` is normalized to
    lowercase colon-separated form when it looks like a MAC address. Signal
    values are normalized to the UI-friendly ``0..100`` range.
    """

    ssid: str | None
    security: WifiSecurity = WifiSecurity.UNKNOWN
    signal_percent: int | None = None
    bssid: str | None = None
    channel: int | None = None
    interface: str | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.ssid is not None and not isinstance(self.ssid, str):
            raise TypeError("ssid must be a string or None")
        if not isinstance(self.security, WifiSecurity):
            object.__setattr__(self, "security", WifiSecurity(str(self.security)))
        if self.signal_percent is not None:
            if not isinstance(self.signal_percent, int):
                raise TypeError("signal_percent must be an integer or None")
            object.__setattr__(self, "signal_percent", max(0, min(100, self.signal_percent)))
        if self.bssid is not None:
            object.__setattr__(self, "bssid", _normalize_bssid(self.bssid))
        if self.channel is not None and self.channel < 0:
            raise ValueError("channel must be non-negative")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")

    @property
    def identity(self) -> tuple[str | None, str | None, str | None]:
        """Stable identity for scan deduplication within an interface.

        Hidden networks without a BSSID intentionally coalesce because the
        host OS provides no stable identifier for distinguishing them. A
        platform adapter that can distinguish those entries should provide a
        BSSID rather than inventing one in the domain model.
        """

        return (self.interface, self.ssid, self.bssid)

    @property
    def display_name(self) -> str:
        """Human-readable label that does not expose credentials."""

        return self.ssid if self.ssid else "<hidden network>"

    def to_dict(self) -> dict[str, Any]:
        """Serialize only fields permitted in investigation events."""

        return {
            "ssid": self.ssid,
            "security": self.security.value,
            "signal_percent": self.signal_percent,
            "bssid": self.bssid,
            "channel": self.channel,
            "interface": self.interface,
            "observed_at": self.observed_at.isoformat(),
        }


@dataclass(frozen=True)
class WifiConnection:
    """A point-in-time host-mediated connection snapshot."""

    network: WifiNetwork
    state: WifiConnectionState = WifiConnectionState.DISCONNECTED
    interface: str | None = None
    ip_address: str | None = None
    gateway: str | None = None
    portal_url: str | None = None
    error: str | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.state, WifiConnectionState):
            object.__setattr__(self, "state", WifiConnectionState(str(self.state)))
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.interface is None and self.network.interface is not None:
            object.__setattr__(self, "interface", self.network.interface)
        if self.state is not WifiConnectionState.CAPTIVE_PORTAL and self.portal_url is not None:
            raise ValueError("portal_url is only valid for a captive-portal connection")

    def transition(
        self,
        state: WifiConnectionState,
        *,
        ip_address: str | None = None,
        gateway: str | None = None,
        portal_url: str | None = None,
        error: str | None = None,
        observed_at: datetime | None = None,
    ) -> WifiConnection:
        """Return a new snapshot after a valid lifecycle transition."""

        target_state = WifiConnectionState(state)
        if target_state not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"invalid Wi-Fi transition: {self.state.value} -> {target_state.value}")
        if target_state is WifiConnectionState.CAPTIVE_PORTAL:
            portal_url = portal_url or self.portal_url
        elif portal_url is not None:
            raise ValueError("portal_url is only valid for a captive-portal connection")
        else:
            portal_url = None
        return WifiConnection(
            network=self.network,
            state=target_state,
            interface=self.interface,
            ip_address=ip_address if ip_address is not None else self.ip_address,
            gateway=gateway if gateway is not None else self.gateway,
            portal_url=portal_url,
            error=error,
            observed_at=observed_at or datetime.now(timezone.utc),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize only safe connection metadata; never credentials."""

        return {
            "network": self.network.to_dict(),
            "state": self.state.value,
            "interface": self.interface,
            "ip_address": self.ip_address,
            "gateway": self.gateway,
            "portal_url": _safe_portal_url(self.portal_url),
            # Adapter errors can include command output or echoed input. Keep
            # the persisted shape useful without retaining arbitrary text.
            "error": "adapter operation failed" if self.error else None,
            "observed_at": self.observed_at.isoformat(),
        }


class CancellationToken:
    """Thread-safe, pollable cancellation token for adapter operations."""

    def __init__(self) -> None:
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation has been requested."""

        return self._event.is_set()

    def cancel(self) -> None:
        """Request cancellation; repeated calls are harmless."""

        self._event.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for cancellation and return whether it was requested."""

        return self._event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        """Raise the typed cancellation error when cancellation was requested."""

        if self.is_cancelled:
            raise WifiOperationCancelled("Wi-Fi operation cancelled")


_ALLOWED_TRANSITIONS: dict[WifiConnectionState, frozenset[WifiConnectionState]] = {
    WifiConnectionState.DISCONNECTED: frozenset(
        {WifiConnectionState.SCANNING, WifiConnectionState.ASSOCIATING, WifiConnectionState.CANCELLED}
    ),
    WifiConnectionState.SCANNING: frozenset(
        {WifiConnectionState.DISCONNECTED, WifiConnectionState.ASSOCIATING, WifiConnectionState.FAILED, WifiConnectionState.CANCELLED}
    ),
    WifiConnectionState.ASSOCIATING: frozenset(
        {WifiConnectionState.CONNECTED, WifiConnectionState.FAILED, WifiConnectionState.CANCELLED, WifiConnectionState.DISCONNECTING}
    ),
    WifiConnectionState.CONNECTED: frozenset(
        {WifiConnectionState.IP_CONFIGURED, WifiConnectionState.DISCONNECTING, WifiConnectionState.FAILED, WifiConnectionState.CANCELLED}
    ),
    WifiConnectionState.IP_CONFIGURED: frozenset(
        {WifiConnectionState.CAPTIVE_PORTAL, WifiConnectionState.ONLINE, WifiConnectionState.DISCONNECTING, WifiConnectionState.FAILED, WifiConnectionState.CANCELLED}
    ),
    WifiConnectionState.CAPTIVE_PORTAL: frozenset(
        {WifiConnectionState.ONLINE, WifiConnectionState.DISCONNECTING, WifiConnectionState.FAILED, WifiConnectionState.CANCELLED}
    ),
    WifiConnectionState.ONLINE: frozenset(
        {WifiConnectionState.DISCONNECTING, WifiConnectionState.FAILED, WifiConnectionState.CANCELLED}
    ),
    WifiConnectionState.DISCONNECTING: frozenset(
        {WifiConnectionState.DISCONNECTED, WifiConnectionState.FAILED, WifiConnectionState.CANCELLED}
    ),
    WifiConnectionState.FAILED: frozenset(
        {WifiConnectionState.DISCONNECTED, WifiConnectionState.ASSOCIATING, WifiConnectionState.CANCELLED}
    ),
    WifiConnectionState.CANCELLED: frozenset({WifiConnectionState.DISCONNECTED, WifiConnectionState.ASSOCIATING}),
}

_MAC_RE = re.compile(r"^[0-9a-fA-F]{12}$")
_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "auth",
        "code",
        "credential",
        "key",
        "otp",
        "pass",
        "password",
        "secret",
        "session",
        "sessionid",
        "session_id",
        "state",
        "token",
        "voucher",
    }
)


def _is_sensitive_query_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _SENSITIVE_QUERY_KEYS or normalized.endswith(
        ("_token", "_secret", "_password", "_credential", "_key")
    )


def _safe_query_value(value: str) -> str:
    # Captured redirect parameters often contain another URL. Sanitize that
    # nested URL too, while leaving ordinary navigation values untouched.
    if "://" in value:
        return _safe_portal_url(value) or "[REDACTED]"
    return value


def _looks_like_token(segment: str) -> bool:
    compact = segment.strip()
    if len(compact) < 24 or not re.fullmatch(r"[A-Za-z0-9_-]+", compact):
        return False
    # Opaque URL-safe identifiers are safer to omit than to persist. This
    # catches lowercase hex, UUID-like values, and base64url-style tokens,
    # while leaving ordinary short portal path labels intact.
    return bool(
        re.fullmatch(r"[0-9a-fA-F]{24,}", compact)
        or re.fullmatch(r"[A-Za-z0-9_-]{32,}", compact)
    )


def _normalize_bssid(value: str) -> str:
    compact = re.sub(r"[:-]", "", value.strip())
    if _MAC_RE.fullmatch(compact):
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2)).lower()
    return value.strip().lower()


def safe_portal_url(value: str | None) -> str | None:
    """Redact sensitive URL components before persistence or evidence."""

    return _safe_portal_url(value)


def _safe_portal_url(value: str | None) -> str | None:
    """Redact sensitive URL components before persistence."""

    if value is None:
        return None
    try:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.hostname:
            return "[redacted-url]"
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        try:
            port = f":{parsed.port}" if parsed.port is not None else ""
        except ValueError:
            return "[redacted-url]"
        query = urlencode(
            [
                (
                    key,
                    "[REDACTED]"
                    if _is_sensitive_query_key(key)
                    else _safe_query_value(item),
                )
                for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            ],
            doseq=True,
        )
        # Fragments are not sent to the server and may contain client-side
        # tokens, so they are never persisted. Opaque path segments are also
        # removed when they resemble high-entropy session identifiers.
        path = "/".join(
            "[REDACTED]" if _looks_like_token(segment) else segment
            for segment in parsed.path.split("/")
        )
        return urlunsplit((parsed.scheme, f"{host}{port}", path, query, ""))
    except (TypeError, ValueError):
        return "[redacted-url]"


__all__ = [
    "CancellationToken",
    "WifiAdapterCapabilities",
    "WifiConnection",
    "WifiConnectionState",
    "WifiNetwork",
    "WifiSecurity",
    "safe_portal_url",
]
