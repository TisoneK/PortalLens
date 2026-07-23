"""Captive Wi-Fi portal plugin.

Importing this package registers :class:`CaptiveWifiPortal` against
:class:`PortalType.CAPTIVE_WIFI` via the plugin registry (see
:mod:`portallens.plugins`).
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
from portallens.plugins.captive_wifi.signatures import (
    SIGNATURES,
    PortalSignature,
    Provenance,
    SignatureLayer,
    SignatureRule,
    platform_for_host,
    platform_for_url,
    signature_for_slug,
)
from portallens.plugins.captive_wifi.url_parser import (
    CaptivePortalFlavor,
    CaptivePortalURLHints,
    looks_like_captive_portal,
    parse_captive_url,
)

__all__ = [
    "SIGNATURES",
    "CaptivePortalFlavor",
    "CaptivePortalURLHints",
    "CaptiveWifiPortal",
    "FingerprintMatch",
    "PortalSignature",
    "Provenance",
    "RelationshipInference",
    "SignatureLayer",
    "SignatureRule",
    "detect_fingerprints",
    "infer_relationships",
    "looks_like_captive_portal",
    "parse_captive_url",
    "platform_for_host",
    "platform_for_url",
    "signature_for_slug",
]
