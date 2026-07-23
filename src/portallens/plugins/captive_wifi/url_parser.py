"""Passive URL parser for captive-portal URLs.

Captive-portal URLs carry a lot of signal in their query strings —
MikroTik hotspots emit ``link-login``, ``link-orig``, ``link-login-only``,
``dst``, ``mac``, ``ip``; ISPMan emits ``hotspots/<id>/<id>/<id>/select``
paths; CoovaChilli emits ``challenge`` and ``userurl``. This module
extracts those hints purely from :mod:`urllib.parse` — no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from portallens.acquisition import ParsedPortalURL, parse_portal_url


class CaptivePortalFlavor(str, Enum):
    """Best-effort classification of the captive-portal URL's emitting
    gateway, based purely on its query-string signature.

    The analyzer uses this as a *hint* — the platform detector in
    :mod:`portallens.plugins.captive_wifi.fingerprints` is what produces
    the final fingerprint with confidence. A URL can match multiple
    flavors (e.g. a MikroTik hotspot fronted by an ISPMan portal will
    show both signatures).
    """

    MIKROTIK = "mikrotik"
    ISPMAN = "ispman"
    COOVACHILLI = "coovachilli"
    GENERIC = "generic"


@dataclass
class CaptivePortalURLHints:
    """Structured hints extracted from a captive-portal URL.

    ``parsed`` is the raw :class:`ParsedPortalURL`. The remaining fields
    are domain-specific extractions that the analyzer turns into
    :class:`Evidence` records.
    """

    parsed: ParsedPortalURL
    flavors: list[CaptivePortalFlavor] = field(default_factory=list)
    mikrotik_link_login: str | None = None
    mikrotik_link_orig: str | None = None
    mikrotik_dst: str | None = None
    mikrotik_mac: str | None = None
    mikrotik_ip: str | None = None
    ispman_hotspot_ids: list[str] = field(default_factory=list)
    coovachilli_challenge: str | None = None
    coovachilli_userurl: str | None = None

    @property
    def host(self) -> str:
        return self.parsed.host

    @property
    def path(self) -> str:
        return self.parsed.path


# Query-string keys MikroTik RouterOS hotspots emit. Documented at
# https://wiki.mikrotik.com/wiki/Hotspot_server_variables and stable
# across ROS versions.
_MIKROTIK_KEYS = {
    "link-login",
    "link-orig",
    "link-login-only",
    "dst",
    "mac",
    "ip",
    "username",
    "error",
    "height",
    "width",
    "platform",
    "timezone",
    "userAgent",
    "webgl",
    "canvasFingerprint",
    "cookie",
}

# ISPMan captive portal URL pattern — observed in the wild:
#   https://captive.ispman.tech/hotspots/<id>/<id>/<id>/ispman-paid/select?...
# The path always starts with /hotspots/ and ends with /select.
_ISPMAN_HOST_SUFFIX = "ispman.tech"
_ISPMAN_PATH_PREFIX = "/hotspots/"
_ISPMAN_PATH_SUFFIX = "/select"

# CoovaChilli query-string keys — documented at
# https://coova.github.io/CoovaChilli/PortalConfig.html
_COOVACHILLI_KEYS = {"challenge", "userurl", "redirurl", "nasid", "uamip", "uamport"}


def parse_captive_url(url: str) -> CaptivePortalURLHints:
    """Parse a captive-portal URL into structured hints.

    Always returns a :class:`CaptivePortalURLHints` — never raises on
    URL shape. An unrecognized URL simply yields an empty hints object
    with ``flavors=[CaptivePortalFlavor.GENERIC]``.
    """

    parsed = parse_portal_url(url)
    hints = CaptivePortalURLHints(parsed=parsed)

    present_keys = {k for k, _ in parsed.query_params}

    # --- MikroTik detection ---------------------------------------------------
    mikrotik_keys_present = present_keys & _MIKROTIK_KEYS
    # The combination of link-login + link-orig + dst is the canonical
    # MikroTik signature — but the entry URL (e.g. maz.wifi/login?dst=...)
    # only carries `dst`. We accept that as a MikroTik hint when the path
    # is `/login` — the canonical MikroTik hotspot login entry point.
    # The fingerprint detector in fingerprints.py weights `dst` low on
    # its own, so a `dst`-only URL produces a low-confidence fingerprint,
    # not a high one.
    full_signature = {"link-login", "link-orig"} <= mikrotik_keys_present or len(mikrotik_keys_present) >= 4
    entry_signature = (
        "dst" in mikrotik_keys_present
        and (parsed.path or "").lower().startswith("/login")
    )
    if full_signature or entry_signature:
        hints.flavors.append(CaptivePortalFlavor.MIKROTIK)
        hints.mikrotik_link_login = parsed.param("link-login")
        hints.mikrotik_link_orig = parsed.param("link-orig")
        hints.mikrotik_dst = parsed.param("dst")
        hints.mikrotik_mac = parsed.param("mac")
        hints.mikrotik_ip = parsed.param("ip")

    # --- ISPMan detection -----------------------------------------------------
    # ISPMan is identified by host suffix + path pattern, not query
    # params — its portal receives the MikroTik-style params via the
    # redirect URL but adds its own path scheme.
    host_lower = parsed.host.lower()
    path = parsed.path or ""
    if (
        host_lower == _ISPMAN_HOST_SUFFIX
        or host_lower.endswith("." + _ISPMAN_HOST_SUFFIX)
    ) and path.startswith(_ISPMAN_PATH_PREFIX) and path.endswith(_ISPMAN_PATH_SUFFIX):
        hints.flavors.append(CaptivePortalFlavor.ISPMAN)
        # Path is /hotspots/<h1>/<h2>/<h3>/<tier>/select — extract the
        # UUID-shaped segments as identifiers. We don't assume they're
        # UUIDs; we just collect the path components between the
        # /hotspots/ prefix and the /<tier>/select suffix.
        middle = path[len(_ISPMAN_PATH_PREFIX):-len(_ISPMAN_PATH_SUFFIX)]
        parts = [p for p in middle.split("/") if p]
        # The last part is the tier name (e.g. "ispman-paid"); the rest
        # are operator/hotspot/session identifiers.
        if parts:
            hints.ispman_hotspot_ids = parts[:-1]

    # --- CoovaChilli detection ------------------------------------------------
    coova_keys_present = present_keys & _COOVACHILLI_KEYS
    if "challenge" in coova_keys_present or {"userurl", "uamip"} <= coova_keys_present:
        hints.flavors.append(CaptivePortalFlavor.COOVACHILLI)
        hints.coovachilli_challenge = parsed.param("challenge")
        hints.coovachilli_userurl = parsed.param("userurl")

    if not hints.flavors:
        hints.flavors.append(CaptivePortalFlavor.GENERIC)

    return hints


def looks_like_captive_portal(url: str) -> bool:
    """Cheap predicate — does this URL look like a captive-portal URL?

    Returns True iff :func:`parse_captive_url` produced at least one
    non-:attr:`CaptivePortalFlavor.GENERIC` flavor. Used by the CLI to
    decide whether the captive_wifi plugin is the right analyzer.
    """

    hints = parse_captive_url(url)
    return any(f != CaptivePortalFlavor.GENERIC for f in hints.flavors)


def same_host(url_a: str, url_b: str) -> bool:
    """True iff the two URLs share a hostname (case-insensitive)."""

    a = urlparse(url_a).hostname or ""
    b = urlparse(url_b).hostname or ""
    return a.lower() == b.lower()
