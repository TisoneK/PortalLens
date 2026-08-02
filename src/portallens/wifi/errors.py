"""Errors raised by the platform-neutral Wi-Fi adapter contract."""

from __future__ import annotations


class WifiError(Exception):
    """Base class for expected Wi-Fi adapter failures."""


class WifiAdapterUnavailable(WifiError):
    """The host has no usable Wi-Fi adapter or required system service."""


class WifiPermissionError(WifiError):
    """The operating system denied the requested Wi-Fi operation."""


class WifiUnsupportedOperation(WifiError):
    """The selected adapter cannot perform the requested operation."""


class WifiOperationTimeout(WifiError):
    """The adapter did not complete an operation within its deadline."""


class WifiOperationCancelled(WifiError):
    """An operation stopped because its cancellation token was cancelled."""


class WifiConnectionError(WifiError):
    """The host OS could not establish or maintain the requested connection."""


__all__ = [
    "WifiAdapterUnavailable",
    "WifiConnectionError",
    "WifiError",
    "WifiOperationCancelled",
    "WifiOperationTimeout",
    "WifiPermissionError",
    "WifiUnsupportedOperation",
]
