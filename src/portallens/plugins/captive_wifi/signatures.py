"""The captive-portal signature registry — provider knowledge as data.

Before this module, every provider PortalLens knew about was a hand-written
branch: an enum member in :mod:`~portallens.plugins.captive_wifi.url_parser`,
a ``_detect_<vendor>`` function in
:mod:`~portallens.plugins.captive_wifi.fingerprints`, and a string literal
(``"ispman.tech"``) in
:mod:`~portallens.plugins.captive_wifi.relationship`. Adding a provider meant
editing four files; the analyzer was *centered* on the one provider it was
first written against.

Here a provider is a :class:`PortalSignature` record. The detectors iterate
the registry; nothing downstream names a vendor.

Two layers
----------
The registry deliberately separates two things the first implementation
conflated:

- :attr:`SignatureLayer.GATEWAY` — the on-premise software that *emits* the
  redirect (MikroTik RouterOS, CoovaChilli, UniFi). Identified by its
  query-string variables, which travel with the redirect.
- :attr:`SignatureLayer.HOSTED_PLATFORM` — a third-party service that *hosts*
  the portal on the operator's behalf (ISPMan, Meraki). Identified by its own
  host + path scheme.

The distinction is what makes relationship inference provider-agnostic: a
redirect landing on any ``HOSTED_PLATFORM`` host supports ``USES_PLATFORM``
and ``AUTHENTICATES_FOR``, and the operator behind the gateway is never the
platform itself. A gateway signature supports neither.

Provenance
----------
Every signature records where its rule came from. PortalLens reports
calibrated claims, so a signature transcribed from vendor documentation but
never checked against a captured URL must not read the same as one validated
against a fixture in ``tests/data/``. :attr:`PortalSignature.provenance` is
surfaced in the fingerprint note so a reader can weigh the match themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from portallens.provenance import Provenance as Provenance


class SignatureLayer(str, Enum):
    """Which layer of the captive-portal stack a signature identifies."""

    GATEWAY = "gateway"
    HOSTED_PLATFORM = "hosted_platform"


@dataclass(frozen=True)
class SignatureRule:
    """One way a signature can fire.

    A rule matches only if *every* constraint it sets is satisfied; a
    signature fires if *any* of its rules match. Empty constraints are
    ignored, so a rule with only ``path_prefixes`` set is a pure path rule.

    - ``params`` — all of these query keys must be present.
    - ``any_params`` — at least one of these query keys must be present.
    - ``min_known_params`` — at least this many of the signature's
      :attr:`PortalSignature.known_params` must be present. Catches gateways
      that emit a large, partially-optional variable set.
    - ``host_suffixes`` — the hostname must equal, or be a subdomain of, one
      of these.
    - ``path_prefixes`` / ``path_suffixes`` — the path must start / end with
      one of these (case-insensitive).
    """

    params: frozenset[str] = frozenset()
    any_params: frozenset[str] = frozenset()
    min_known_params: int = 0
    host_suffixes: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    path_suffixes: tuple[str, ...] = ()

    def matches(self, *, host: str, path: str, present_params: frozenset[str], known: frozenset[str]) -> bool:
        """True iff every constraint this rule sets is satisfied."""

        return all(
            (
                not self.params or self.params <= present_params,
                not self.any_params or bool(self.any_params & present_params),
                len(known & present_params) >= self.min_known_params,
                not self.host_suffixes or host_matches(host, self.host_suffixes),
                not self.path_prefixes or any(path.startswith(p.lower()) for p in self.path_prefixes),
                not self.path_suffixes or any(path.endswith(s.lower()) for s in self.path_suffixes),
            )
        )


@dataclass(frozen=True)
class PortalSignature:
    """Everything PortalLens knows about one captive-portal platform.

    ``slug`` is the stable identifier used as a URL "flavor" (see
    :class:`~portallens.plugins.captive_wifi.url_parser.CaptivePortalFlavor`,
    which enumerates the built-in slugs for convenience — a signature added
    here needs no enum member). ``platform`` is the display name that lands
    in :class:`~portallens.portal.PortalFingerprint`.

    The weights are what the fingerprint detector feeds to
    :func:`portallens.confidence.score` (noisy-OR, per ADR-2): each present
    query parameter contributes ``param_weights[key]``, a host match
    contributes ``host_weight``, and a path match contributes ``path_weight``.
    """

    slug: str
    platform: str
    layer: SignatureLayer
    rules: tuple[SignatureRule, ...]
    note: str
    provenance: Provenance = Provenance.DOCUMENTED
    known_params: frozenset[str] = frozenset()
    param_weights: dict[str, int] = field(default_factory=dict)
    #: Parameters whose value is a URL pointing BACK at the gateway that
    #: redirected the client here. These drive redirect inference. A
    #: parameter naming the user's *original* destination (MikroTik's
    #: ``link-orig``, CoovaChilli's ``userurl``) must never be listed here —
    #: it is not a portal redirect, and treating it as one invents
    #: relationships to whatever site the client happened to be loading.
    backlink_params: frozenset[str] = frozenset()
    host_suffixes: tuple[str, ...] = ()
    host_weight: int = 0
    path_weight: int = 0
    # Path-borne identifiers (operator / hotspot / session ids). The segments
    # between ``path_id_prefix`` and ``path_id_suffix`` are extracted, minus
    # the last ``path_id_drop_trailing`` of them (typically a tier or plan
    # name rather than an identifier).
    path_id_prefix: str | None = None
    path_id_suffix: str | None = None
    path_id_drop_trailing: int = 0

    @property
    def is_hosted_platform(self) -> bool:
        return self.layer is SignatureLayer.HOSTED_PLATFORM

    def matches(self, *, host: str, path: str, present_params: frozenset[str]) -> bool:
        """True iff any of this signature's rules matches the URL parts."""

        host = host.lower()
        path = (path or "").lower()
        return any(
            rule.matches(host=host, path=path, present_params=present_params, known=self.known_params)
            for rule in self.rules
        )

    def owns_host(self, host: str) -> bool:
        """True iff ``host`` belongs to this signature's operator.

        Only meaningful for hosted platforms — a gateway runs on whatever
        hostname the local operator chose, so it owns no hostname of its own.
        """

        return bool(self.host_suffixes) and host_matches(host, self.host_suffixes)

    def path_ids(self, path: str) -> list[str]:
        """Extract path-borne identifiers, or ``[]`` if this signature
        declares none (or the path doesn't carry them)."""

        if self.path_id_prefix is None or self.path_id_suffix is None:
            return []
        lowered = (path or "").lower()
        if not (lowered.startswith(self.path_id_prefix.lower()) and lowered.endswith(self.path_id_suffix.lower())):
            return []
        middle = path[len(self.path_id_prefix) : len(path) - len(self.path_id_suffix)]
        parts = [p for p in middle.split("/") if p]
        if self.path_id_drop_trailing:
            parts = parts[: -self.path_id_drop_trailing] or []
        return parts


def host_matches(host: str, suffixes: tuple[str, ...]) -> bool:
    """True iff ``host`` equals, or is a subdomain of, one of ``suffixes``.

    Suffix matching is done on label boundaries — ``evilispman.tech`` does not
    match ``ispman.tech``.
    """

    host = host.lower().rstrip(".")
    return any(host == s.lower() or host.endswith("." + s.lower()) for s in suffixes)


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

# MikroTik RouterOS hotspot login variables, documented at
# https://wiki.mikrotik.com/wiki/Hotspot_server_variables and stable across
# ROS versions. Semantics differ per parameter and matter downstream:
#   link-login       the hotspot's own login page (a back-reference)
#   link-login-only  same, without the original-destination round trip
#   link-orig        the URL the user was originally trying to reach — NOT a
#                    portal redirect (see relationship.py; treating it as one
#                    produced a false positive in session 1)
_MIKROTIK_PARAMS = frozenset(
    {
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
)

MIKROTIK = PortalSignature(
    slug="mikrotik",
    platform="MikroTik RouterOS Hotspot",
    layer=SignatureLayer.GATEWAY,
    provenance=Provenance.VALIDATED,
    known_params=_MIKROTIK_PARAMS,
    rules=(
        # The canonical signature: the login back-reference plus the original
        # destination.
        SignatureRule(params=frozenset({"link-login", "link-orig"})),
        # A broad slice of the variable set is equally conclusive even when
        # the two canonical keys are absent.
        SignatureRule(min_known_params=4),
        # The entry URL (e.g. maz.wifi/login?dst=...) carries only `dst`. That
        # is a hint, not a detection — the weights below keep a dst-only URL
        # at low confidence.
        SignatureRule(any_params=frozenset({"dst"}), path_prefixes=("/login",)),
    ),
    param_weights={
        "link-login": 55,
        "link-login-only": 45,
        "link-orig": 40,
        "dst": 20,
        "mac": 10,
        "ip": 10,
    },
    backlink_params=frozenset({"link-login", "link-login-only"}),
    note="Query-string signature matches MikroTik RouterOS hotspot login variables.",
)

# CoovaChilli portal variables, documented at
# https://coova.github.io/CoovaChilli/PortalConfig.html
COOVACHILLI = PortalSignature(
    slug="coovachilli",
    platform="CoovaChilli",
    layer=SignatureLayer.GATEWAY,
    provenance=Provenance.DOCUMENTED,
    known_params=frozenset({"challenge", "userurl", "redirurl", "nasid", "uamip", "uamport"}),
    rules=(
        # `challenge` is CoovaChilli-specific enough to fire on its own.
        SignatureRule(any_params=frozenset({"challenge"})),
        # `userurl` and `uamip` are individually weaker; together they are the
        # documented UAM redirect pair.
        SignatureRule(params=frozenset({"userurl", "uamip"})),
    ),
    param_weights={
        "challenge": 55,
        "uamip": 35,
        "uamport": 35,
        "nasid": 35,
        "userurl": 30,
    },
    note="Query-string signature matches CoovaChilli captive-portal variables.",
)

# Ubiquiti UniFi guest portal. The controller serves the splash page under
# /guest/s/<site>/ and passes the client MAC as `id`, the AP MAC as `ap`, and
# the originally-requested URL as `url`. The path prefix carries the
# signature — the parameter names on their own are far too generic.
UNIFI = PortalSignature(
    slug="unifi",
    platform="Ubiquiti UniFi Guest Portal",
    layer=SignatureLayer.GATEWAY,
    provenance=Provenance.DOCUMENTED,
    known_params=frozenset({"id", "ap", "t", "url", "ssid"}),
    rules=(SignatureRule(path_prefixes=("/guest/s/",), any_params=frozenset({"id", "ap", "ssid"})),),
    param_weights={"id": 30, "ap": 30, "ssid": 20, "t": 10, "url": 10},
    path_weight=45,
    note="URL path matches the UniFi controller guest-portal scheme (/guest/s/<site>/).",
)

# ISPMan hosted captive portal — observed in the wild as
#   https://captive.ispman.tech/hotspots/<id>/<id>/<id>/<tier>/select?...
# Host suffix and path scheme together are conclusive; the MikroTik-style
# query parameters on the same URL belong to the gateway that redirected
# here, not to ISPMan.
ISPMAN = PortalSignature(
    slug="ispman",
    platform="ISPMan",
    layer=SignatureLayer.HOSTED_PLATFORM,
    provenance=Provenance.VALIDATED,
    rules=(
        SignatureRule(
            host_suffixes=("ispman.tech",),
            path_prefixes=("/hotspots/",),
            path_suffixes=("/select",),
        ),
    ),
    host_suffixes=("ispman.tech",),
    host_weight=60,
    path_weight=50,
    path_id_prefix="/hotspots/",
    path_id_suffix="/select",
    # Trailing segment is the tier/plan name (e.g. "ispman-paid"), not an id.
    path_id_drop_trailing=1,
    note="URL host + path match the ISPMan captive-portal scheme (captive.ispman.tech/hotspots/.../select).",
)

# Cisco Meraki cloud-hosted splash pages are served from the shared
# network-auth.com domain (e.g. n143.network-auth.com/splash/...). The
# hostname is Meraki's, not the operator's — which is exactly what makes it a
# hosted platform rather than a gateway.
MERAKI = PortalSignature(
    slug="meraki",
    platform="Cisco Meraki Splash",
    layer=SignatureLayer.HOSTED_PLATFORM,
    provenance=Provenance.DOCUMENTED,
    rules=(SignatureRule(host_suffixes=("network-auth.com",), path_prefixes=("/splash/",)),),
    host_suffixes=("network-auth.com",),
    host_weight=55,
    path_weight=40,
    note="URL host + path match the Cisco Meraki cloud splash-page scheme (*.network-auth.com/splash/).",
)


SIGNATURES: tuple[PortalSignature, ...] = (
    # Gateways first, then hosted platforms — this order determines the order
    # of `CaptivePortalURLHints.flavors`.
    MIKROTIK,
    COOVACHILLI,
    UNIFI,
    ISPMAN,
    MERAKI,
)

GATEWAY_SIGNATURES: tuple[PortalSignature, ...] = tuple(
    s for s in SIGNATURES if s.layer is SignatureLayer.GATEWAY
)
HOSTED_PLATFORM_SIGNATURES: tuple[PortalSignature, ...] = tuple(
    s for s in SIGNATURES if s.layer is SignatureLayer.HOSTED_PLATFORM
)


def signature_for_slug(slug: str) -> PortalSignature | None:
    """Look a signature up by its slug."""

    return next((s for s in SIGNATURES if s.slug == slug), None)


def platform_for_host(host: str) -> PortalSignature | None:
    """Return the hosted-platform signature that owns ``host``, if any.

    This is the provider-agnostic replacement for the ``host == "ispman.tech"``
    checks the relationship analyzer used to carry. A host owned by a hosted
    platform is never the local network operator.
    """

    if not host:
        return None
    return next((s for s in HOSTED_PLATFORM_SIGNATURES if s.owns_host(host)), None)


def platform_for_url(url: str) -> PortalSignature | None:
    """Same as :func:`platform_for_host`, taking a full URL."""

    return platform_for_host((urlparse(url).hostname or "").lower())


#: Every backlink parameter any registered signature declares. Relationship
#: inference treats these — and only these — as portal redirects.
BACKLINK_PARAMS: frozenset[str] = frozenset().union(*(s.backlink_params for s in SIGNATURES))
