"""Passive URL parser for captive-portal URLs.

Captive-portal URLs carry a lot of signal in their query strings and paths.
Which signals belong to which platform is not encoded here — it lives in
:mod:`portallens.plugins.captive_wifi.signatures`, and this module just runs
every registered signature against the parsed URL. Adding a provider is a
registry entry, never an edit to this file.

Everything here is derived from :mod:`urllib.parse` — no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from portallens.acquisition import ParsedPortalURL, parse_portal_url
from portallens.plugins.captive_wifi.signatures import (
    SIGNATURES,
    PortalSignature,
    SignatureLayer,
)


class CaptivePortalFlavor(str, Enum):
    """The built-in signature slugs, as an enum for convenient reference.

    ``CaptivePortalURLHints.flavors`` holds plain slug strings, not members of
    this enum — a signature added to the registry works without an enum member
    here. These members exist so callers can write
    ``CaptivePortalFlavor.MIKROTIK in hints.flavors`` instead of a bare string
    literal; comparison works because the enum derives from :class:`str`.
    """

    MIKROTIK = "mikrotik"
    COOVACHILLI = "coovachilli"
    UNIFI = "unifi"
    ISPMAN = "ispman"
    MERAKI = "meraki"
    GENERIC = "generic"


GENERIC_FLAVOR = CaptivePortalFlavor.GENERIC.value


@dataclass
class CaptivePortalURLHints:
    """Structured hints extracted from a captive-portal URL.

    ``parsed`` is the raw :class:`ParsedPortalURL`. ``flavors`` holds the slug
    of every signature that fired (or ``"generic"`` if none did). A URL can
    match several — the ISPMan fixture matches ``ispman`` (its own host+path
    scheme) *and* ``mikrotik`` (the gateway variables forwarded by the
    redirect), because those describe two different layers of the same stack.
    """

    parsed: ParsedPortalURL
    flavors: list[str] = field(default_factory=list)
    #: The hosted-platform signature this URL is served by, if any.
    platform: PortalSignature | None = None
    #: Identifiers carried in the platform's path scheme (operator / hotspot /
    #: session ids), in path order.
    platform_path_ids: list[str] = field(default_factory=list)
    mikrotik_link_login: str | None = None
    mikrotik_link_orig: str | None = None
    mikrotik_dst: str | None = None
    mikrotik_mac: str | None = None
    mikrotik_ip: str | None = None
    coovachilli_challenge: str | None = None
    coovachilli_userurl: str | None = None

    @property
    def host(self) -> str:
        return self.parsed.host

    @property
    def path(self) -> str:
        return self.parsed.path

    @property
    def gateways(self) -> list[PortalSignature]:
        """Every gateway signature that fired on this URL."""

        return [s for s in SIGNATURES if s.layer is SignatureLayer.GATEWAY and s.slug in self.flavors]

    @property
    def is_generic(self) -> bool:
        """True iff no signature matched."""

        return self.flavors == [GENERIC_FLAVOR]


def parse_captive_url(url: str) -> CaptivePortalURLHints:
    """Parse a captive-portal URL into structured hints.

    Always returns a :class:`CaptivePortalURLHints` — never raises on URL
    shape. An unrecognized URL yields ``flavors == ["generic"]``.
    """

    parsed = parse_portal_url(url)
    hints = CaptivePortalURLHints(parsed=parsed)

    present_params = frozenset(k for k, _ in parsed.query_params)
    host = parsed.host
    path = parsed.path or ""

    for signature in SIGNATURES:
        if not signature.matches(host=host, path=path, present_params=present_params):
            continue
        hints.flavors.append(signature.slug)
        if signature.is_hosted_platform and hints.platform is None:
            hints.platform = signature
            hints.platform_path_ids = signature.path_ids(path)

    # Convenience accessors for the two gateways whose parameters the rest of
    # the analyzer reasons about by name. These are pure sugar over
    # `parsed.param(...)` — a new signature needs none of this.
    if CaptivePortalFlavor.MIKROTIK in hints.flavors:
        hints.mikrotik_link_login = parsed.param("link-login")
        hints.mikrotik_link_orig = parsed.param("link-orig")
        hints.mikrotik_dst = parsed.param("dst")
        hints.mikrotik_mac = parsed.param("mac")
        hints.mikrotik_ip = parsed.param("ip")
    if CaptivePortalFlavor.COOVACHILLI in hints.flavors:
        hints.coovachilli_challenge = parsed.param("challenge")
        hints.coovachilli_userurl = parsed.param("userurl")

    if not hints.flavors:
        hints.flavors.append(GENERIC_FLAVOR)

    return hints


def looks_like_captive_portal(url: str) -> bool:
    """Cheap predicate — does this URL look like a captive-portal URL?

    Returns True iff :func:`parse_captive_url` matched at least one registered
    signature. Used by the CLI to decide whether the captive_wifi plugin is
    the right analyzer.
    """

    return not parse_captive_url(url).is_generic


def same_host(url_a: str, url_b: str) -> bool:
    """True iff the two URLs share a hostname (case-insensitive)."""

    a = urlparse(url_a).hostname or ""
    b = urlparse(url_b).hostname or ""
    return a.lower() == b.lower()
