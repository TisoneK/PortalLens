"""Captive Wi-Fi portal plugin.

Registers :class:`CaptiveWifiPortal` against :attr:`PortalType.CAPTIVE_WIFI`.
Importing this module is what makes the captive Wi-Fi analyzer available
to the CLI and the registry.
"""

from __future__ import annotations

from portallens.plugins.captive_wifi.analyzer import CaptiveWifiPortal
from portallens.plugins.captive_wifi.fingerprints import (
    FingerprintMatch,
    detect_fingerprints,
)
from portallens.plugins.captive_wifi.relationship import (
    RelationshipInference,
    infer_relationships,
)
from portallens.plugins.captive_wifi.url_parser import (
    CaptivePortalURLHints,
    parse_captive_url,
)
from portallens.portal import PortalType
from portallens.registry import register_portal

__all__ = [
    "CaptivePortalURLHints",
    "CaptiveWifiPortal",
    "FingerprintMatch",
    "RelationshipInference",
    "detect_fingerprints",
    "infer_relationships",
    "parse_captive_url",
]

# Register on import — the CLI imports this module to make the analyzer live.
register_portal(PortalType.CAPTIVE_WIFI)(CaptiveWifiPortal)
