"""Bounded captive-portal connectivity detection.

This module probes only fixed connectivity-check endpoints or an explicitly
provisioned RFC 8908 API endpoint. It never follows redirects, opens a
browser, submits credentials, or invokes a bypass probe. Results are
allow-listed evidence suitable for a later live-event persistence layer.
Linux coverage intentionally uses the stable GNOME and Firefox profiles;
distro-specific endpoints are deferred because their contracts vary by
desktop environment and distribution.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any
from urllib.parse import urlsplit

import httpx

from portallens.acquisition import assert_policy
from portallens.evidence import Evidence, EvidenceType
from portallens.portal import AcquisitionPolicy, AnalysisContext, PortalReport
from portallens.wifi.errors import WifiOperationCancelled
from portallens.wifi.models import (
    CancellationToken,
    WifiConnection,
    WifiConnectionState,
    safe_portal_url,
)

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_BODY_BYTES = 64 * 1024


class WifiProbePlatform(str, Enum):
    """Platform or standards family represented by a probe profile."""

    WINDOWS = "windows"
    APPLE = "apple"
    ANDROID = "android"
    GNOME = "gnome"
    FIREFOX = "firefox"
    CAPPORT = "capport"


@dataclass(frozen=True)
class CaptivePortalProbeProfile:
    """A fixed endpoint and its expected unrestricted response."""

    name: str
    platform: WifiProbePlatform
    url: str
    expected_statuses: tuple[int, ...]
    expected_body_marker: str | None = None
    headers: tuple[tuple[str, str], ...] = (("User-Agent", "PortalLens/0.1"),)

    def request_headers(self) -> dict[str, str]:
        """Return the profile's request headers as a mutable request mapping."""

        return dict(self.headers)


WINDOWS_NCSI = CaptivePortalProbeProfile(
    name="windows-ncsi",
    platform=WifiProbePlatform.WINDOWS,
    url="http://www.msftncsi.com/ncsi.txt",
    expected_statuses=(200,),
    expected_body_marker="Microsoft NCSI",
)
WINDOWS_CONNECT_TEST = CaptivePortalProbeProfile(
    name="windows-connect-test",
    platform=WifiProbePlatform.WINDOWS,
    url="http://www.msftconnecttest.com/connecttest.txt",
    expected_statuses=(200,),
    expected_body_marker="Microsoft Connect Test",
)
APPLE_HOTSPOT = CaptivePortalProbeProfile(
    name="apple-hotspot",
    platform=WifiProbePlatform.APPLE,
    url="http://captive.apple.com/hotspot-detect.html",
    expected_statuses=(200,),
    expected_body_marker="Success",
)
ANDROID_GENERATE_204 = CaptivePortalProbeProfile(
    name="android-generate-204",
    platform=WifiProbePlatform.ANDROID,
    url="http://connectivitycheck.gstatic.com/generate_204",
    expected_statuses=(204,),
)
ANDROID_CLIENTS3_GENERATE_204 = CaptivePortalProbeProfile(
    name="android-clients3-generate-204",
    platform=WifiProbePlatform.ANDROID,
    url="http://clients3.google.com/generate_204",
    expected_statuses=(204,),
)
GNOME_NETWORK_STATUS = CaptivePortalProbeProfile(
    name="gnome-network-status",
    platform=WifiProbePlatform.GNOME,
    url="http://nmcheck.gnome.org/check_network_status.txt",
    expected_statuses=(200,),
    expected_body_marker="NetworkManager is online",
)
FIREFOX_CANONICAL = CaptivePortalProbeProfile(
    name="firefox-canonical",
    platform=WifiProbePlatform.FIREFOX,
    url="http://detectportal.firefox.com/canonical.html",
    expected_statuses=(200,),
    expected_body_marker="success",
)

PROBE_PROFILES: tuple[CaptivePortalProbeProfile, ...] = (
    WINDOWS_NCSI,
    WINDOWS_CONNECT_TEST,
    APPLE_HOTSPOT,
    ANDROID_GENERATE_204,
    ANDROID_CLIENTS3_GENERATE_204,
    GNOME_NETWORK_STATUS,
    FIREFOX_CANONICAL,
)


@dataclass(frozen=True)
class CaptivePortalResponse:
    """Bounded HTTP response data retained by the detector."""

    status_code: int
    headers: Mapping[str, str]
    body: str
    body_truncated: bool = False


@dataclass(frozen=True)
class CaptivePortalMetadata:
    """Validated RFC 8908 Captive Portal API fields."""

    captive: bool
    user_portal_url: str | None = None
    venue_info_url: str | None = None
    can_extend_session: bool | None = None
    seconds_remaining: int | float | None = None
    bytes_remaining: int | float | None = None


@dataclass(frozen=True)
class CaptivePortalProbeResult:
    """Safe result of one connectivity probe."""

    profile_name: str
    probe_url: str
    captive: bool | None
    status_code: int | None
    portal_url: str | None = None
    error: str | None = None
    body_truncated: bool = False
    metadata: CaptivePortalMetadata | None = None
    evidence: tuple[Evidence, ...] = ()

    @property
    def analysis_urls(self) -> tuple[str, ...]:
        """Return only a validated portal URL for passive analyzer handoff."""

        safe_url = _safe_http_url(self.portal_url)
        return (safe_url,) if safe_url is not None else ()

    def analysis_context(self, *, notes: str | None = None) -> AnalysisContext:
        """Build a passive analyzer context from the detected portal URL."""

        if self.captive is not True or not self.analysis_urls:
            raise ValueError("probe result must confirm captivity and contain a validated portal URL")
        return AnalysisContext(urls=list(self.analysis_urls), user_notes=notes)


ProbeRequest = Callable[
    [str, Mapping[str, str], CancellationToken, float, int], CaptivePortalResponse
]


def profiles_for_platform(platform: WifiProbePlatform | str) -> tuple[CaptivePortalProbeProfile, ...]:
    """Return the fixed legacy profiles for a platform."""

    selected = WifiProbePlatform(platform)
    return tuple(profile for profile in PROBE_PROFILES if profile.platform is selected)


def parse_captive_portal_metadata(payload: str | bytes) -> CaptivePortalMetadata:
    """Parse and validate the RFC 8908 Captive Portal API JSON object.

    Portal URLs are accepted only over HTTPS and are normalized through the
    same persistence-safe URL redaction used by Wi-Fi connection snapshots.
    Unknown fields are ignored; required and known fields are type-checked.
    """

    try:
        raw: Any = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("captive portal API returned invalid JSON") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("captive"), bool):
        raise ValueError("captive portal API JSON must contain a boolean 'captive' field")

    return CaptivePortalMetadata(
        captive=raw["captive"],
        user_portal_url=_validated_https_url(raw.get("user-portal-url")),
        venue_info_url=_validated_https_url(raw.get("venue-info-url")),
        can_extend_session=_optional_bool(raw.get("can-extend-session"), "can-extend-session"),
        seconds_remaining=_optional_number(raw.get("seconds-remaining"), "seconds-remaining"),
        bytes_remaining=_optional_number(raw.get("bytes-remaining"), "bytes-remaining"),
    )


class CaptivePortalDetector:
    """Run one bounded, non-following connectivity probe."""

    def __init__(
        self,
        *,
        request: ProbeRequest | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self._request = request or _http_request
        self._timeout_seconds = timeout_seconds
        self._max_body_bytes = max_body_bytes

    def probe(
        self,
        profile: CaptivePortalProbeProfile,
        policy: AcquisitionPolicy,
        *,
        cancel: CancellationToken | None = None,
    ) -> CaptivePortalProbeResult:
        """Probe a fixed profile; redirects are captured, never followed."""

        assert_policy(policy, "captive_portal_probe")
        profile = _canonical_profile(profile)
        token = cancel or CancellationToken()
        token.raise_if_cancelled()
        try:
            response = self._request(
                profile.url,
                profile.request_headers(),
                token,
                self._timeout_seconds,
                self._max_body_bytes,
            )
        except WifiOperationCancelled:
            raise
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            return CaptivePortalProbeResult(
                profile_name=profile.name,
                probe_url=profile.url,
                captive=None,
                status_code=None,
                error=type(exc).__name__,
                evidence=(
                    _evidence(
                        EvidenceType.CAPTIVE_PORTAL_STATUS,
                        profile,
                        "probe:error",
                        "unavailable",
                        f"Connectivity probe failed with {type(exc).__name__}.",
                    ),
                ),
            )
        token.raise_if_cancelled()
        return _interpret_legacy_response(profile, response)

    def probe_rfc8908(
        self,
        endpoint: str,
        policy: AcquisitionPolicy,
        *,
        provisioned: bool = False,
        cancel: CancellationToken | None = None,
    ) -> CaptivePortalProbeResult:
        """Query an explicitly provisioned HTTPS RFC 8908 API endpoint.

        ``provisioned`` is a required caller assertion that the endpoint came
        from a trusted DHCP/RA captive-portal option or equivalent OS source;
        arbitrary user-entered HTTPS URLs are rejected by default.
        """

        assert_policy(policy, "captive_portal_api")
        request_endpoint = _require_https_url(endpoint)
        if not provisioned:
            raise ValueError("RFC 8908 endpoint must be explicitly provisioned")
        persisted_endpoint = safe_portal_url(request_endpoint)
        if persisted_endpoint is None:
            raise ValueError("RFC 8908 endpoint must be an HTTPS URL")
        token = cancel or CancellationToken()
        token.raise_if_cancelled()
        headers = {
            "Accept": "application/captive+json",
            "User-Agent": "PortalLens/0.1",
        }
        profile = CaptivePortalProbeProfile(
            name="rfc-8908-api",
            platform=WifiProbePlatform.CAPPORT,
            url=persisted_endpoint,
            expected_statuses=(200,),
            headers=tuple(headers.items()),
        )
        try:
            response = self._request(
                request_endpoint,
                headers,
                token,
                self._timeout_seconds,
                self._max_body_bytes,
            )
        except WifiOperationCancelled:
            raise
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            return CaptivePortalProbeResult(
                profile_name=profile.name,
                probe_url=persisted_endpoint,
                captive=None,
                status_code=None,
                error=type(exc).__name__,
                evidence=(
                    _evidence(
                        EvidenceType.CAPTIVE_PORTAL_STATUS,
                        profile,
                        "probe:error",
                        "unavailable",
                        f"RFC 8908 probe failed with {type(exc).__name__}.",
                    ),
                ),
            )
        token.raise_if_cancelled()
        content_type = _header_value(response.headers, "content-type")
        if content_type.lower().split(";", 1)[0].strip() != "application/captive+json":
            return CaptivePortalProbeResult(
                profile_name=profile.name,
                probe_url=persisted_endpoint,
                captive=None,
                status_code=response.status_code,
                body_truncated=response.body_truncated,
                error="unexpected-content-type",
                evidence=(
                    _evidence(
                        EvidenceType.CAPTIVE_PORTAL_METADATA,
                        profile,
                        "metadata:content-type",
                        content_type or "missing",
                        "RFC 8908 API response did not use application/captive+json.",
                    ),
                ),
            )
        if response.status_code != 200:
            return CaptivePortalProbeResult(
                profile_name=profile.name,
                probe_url=persisted_endpoint,
                captive=None,
                status_code=response.status_code,
                body_truncated=response.body_truncated,
                error="unexpected-status",
                evidence=(
                    _evidence(
                        EvidenceType.CAPTIVE_PORTAL_STATUS,
                        profile,
                        "probe:status",
                        str(response.status_code),
                        "RFC 8908 API did not return HTTP 200.",
                    ),
                ),
            )
        try:
            metadata = parse_captive_portal_metadata(response.body)
        except ValueError as exc:
            return CaptivePortalProbeResult(
                profile_name=profile.name,
                probe_url=persisted_endpoint,
                captive=None,
                status_code=response.status_code,
                body_truncated=response.body_truncated,
                error="invalid-metadata",
                evidence=(
                    _evidence(
                        EvidenceType.CAPTIVE_PORTAL_METADATA,
                        profile,
                        "metadata:invalid",
                        "unavailable",
                        str(exc),
                    ),
                ),
            )
        portal_url = metadata.user_portal_url if metadata.captive else None
        evidence = [
            _evidence(
                EvidenceType.CAPTIVE_PORTAL_STATUS,
                profile,
                "probe:status",
                "captive" if metadata.captive else "unrestricted",
                "RFC 8908 API reported the network state.",
            ),
            _evidence(
                EvidenceType.CAPTIVE_PORTAL_METADATA,
                profile,
                "metadata:captive",
                str(metadata.captive).lower(),
                "Parsed from the RFC 8908 Captive Portal API response.",
            ),
        ]
        if portal_url is not None:
            evidence.append(
                _evidence(
                    EvidenceType.CAPTIVE_PORTAL_REDIRECT,
                    profile,
                    "metadata:user-portal-url",
                    portal_url,
                    "Validated HTTPS user portal URL from RFC 8908 metadata.",
                )
            )
        return CaptivePortalProbeResult(
            profile_name=profile.name,
            probe_url=persisted_endpoint,
            captive=metadata.captive,
            status_code=response.status_code,
            portal_url=portal_url,
            body_truncated=response.body_truncated,
            metadata=metadata,
            evidence=tuple(evidence),
        )


def apply_probe_result(
    connection: WifiConnection,
    result: CaptivePortalProbeResult,
) -> WifiConnection:
    """Apply a definitive probe result to an IP-configured host snapshot.

    This is an integration seam for the future selected-session worker. It
    does not connect, disconnect, or start a probe itself.
    """

    if result.captive is None:
        return connection
    if connection.state not in {
        WifiConnectionState.IP_CONFIGURED,
        WifiConnectionState.CAPTIVE_PORTAL,
    }:
        raise ValueError("portal detection requires an IP-configured connection")
    if result.captive:
        if result.portal_url is not None and _safe_http_url(result.portal_url) is None:
            raise ValueError("probe portal_url must be an absolute HTTP(S) URL without credentials")
        portal_url = _safe_http_url(result.portal_url) or connection.portal_url
        if connection.state is WifiConnectionState.CAPTIVE_PORTAL:
            if portal_url == connection.portal_url:
                return connection
            return replace(connection, portal_url=portal_url)
        return connection.transition(
            WifiConnectionState.CAPTIVE_PORTAL,
            portal_url=portal_url,
        )
    return connection.transition(WifiConnectionState.ONLINE)


def _interpret_legacy_response(
    profile: CaptivePortalProbeProfile,
    response: CaptivePortalResponse,
) -> CaptivePortalProbeResult:
    """Classify a legacy probe without retaining arbitrary response bodies."""

    location = _safe_http_url(_header_value(response.headers, "location"))
    evidence: list[Evidence] = [
        _evidence(
            EvidenceType.CAPTIVE_PORTAL_STATUS,
            profile,
            "probe:status",
            str(response.status_code),
            "Captured without following redirects.",
        )
    ]
    if location is not None:
        evidence.append(
            _evidence(
                EvidenceType.CAPTIVE_PORTAL_REDIRECT,
                profile,
                "redirect:location",
                location,
                "Redirect target was captured but not requested.",
            )
        )
    if response.status_code in {301, 302, 303, 307, 308} and location is not None:
        captive: bool | None = True
        portal_url = location
        note = "Connectivity probe was redirected; a captive portal is indicated."
    elif 300 <= response.status_code < 400:
        captive = None
        portal_url = None
        note = "Connectivity probe returned a redirect-like status without a valid Location."
    elif response.status_code not in profile.expected_statuses:
        captive = None
        portal_url = None
        note = "Connectivity probe returned a non-success status; captivity is unknown."
    elif profile.expected_body_marker is None:
        captive = False
        portal_url = None
        note = "Connectivity probe returned its expected unrestricted status."
    elif profile.expected_body_marker in response.body:
        captive = False
        portal_url = None
        note = "Connectivity probe returned its expected unrestricted body marker."
    elif response.body_truncated:
        captive = None
        portal_url = None
        note = "Response was capped before the expected success marker could be verified."
    elif _looks_like_portal_body(response.body):
        captive = None
        portal_url = None
        note = "Expected success status returned possible portal content; captivity is unconfirmed."
    else:
        captive = None
        portal_url = None
        note = "Expected success status returned unrecognized content; captivity is unknown."
    evidence.append(
        _evidence(
            EvidenceType.CAPTIVE_PORTAL_STATUS,
            profile,
            "probe:classification",
            "captive" if captive is True else "unrestricted" if captive is False else "unknown",
            note,
        )
    )
    return CaptivePortalProbeResult(
        profile_name=profile.name,
        probe_url=profile.url,
        captive=captive,
        status_code=response.status_code,
        portal_url=portal_url,
        body_truncated=response.body_truncated,
        evidence=tuple(evidence),
    )


def _http_request(
    url: str,
    headers: Mapping[str, str],
    cancel: CancellationToken,
    timeout_seconds: float,
    max_body_bytes: int,
) -> CaptivePortalResponse:
    """Perform one capped GET with redirects disabled."""

    cancel.raise_if_cancelled()
    body = bytearray()
    truncated = False
    with (
        httpx.Client(
            follow_redirects=False,
            timeout=timeout_seconds,
            max_redirects=0,
        ) as client,
        client.stream("GET", url, headers=dict(headers)) as response,
    ):
        for chunk in response.iter_bytes(chunk_size=4096):
            cancel.raise_if_cancelled()
            remaining = max_body_bytes - len(body)
            if remaining <= 0:
                truncated = True
                break
            body.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
                break
        # An exact-cap response may have more bytes that were not observable
        # after the bounded read. Treat it conservatively as truncated.
        if len(body) == max_body_bytes:
            truncated = True
        return CaptivePortalResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=bytes(body).decode(response.encoding or "utf-8", errors="replace"),
            body_truncated=truncated,
        )


def _require_https_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("portal API URL fields must be strings")
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("portal API URL fields must be absolute HTTPS URLs")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("portal API URL fields must not contain credentials")
    return value


def _validated_https_url(value: Any) -> str | None:
    if value is None:
        return None
    return safe_portal_url(_require_https_url(value))


def _safe_http_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return safe_portal_url(value)


def _looks_like_portal_body(body: str) -> bool:
    """Recognize only coarse, non-provider-specific captive-page markers."""

    lowered = body.lower()
    return any(marker in lowered for marker in ("<form", "captive", "portal", "login"))


def _canonical_profile(profile: CaptivePortalProbeProfile) -> CaptivePortalProbeProfile:
    """Return an allow-listed legacy profile or reject arbitrary URLs."""

    for known in PROBE_PROFILES:
        if profile is known or (profile.name == known.name and profile.url == known.url):
            return known
    raise ValueError("legacy captive-portal probes must use a built-in profile")


def _header_value(headers: Mapping[str, str], name: str) -> str:
    """Read an HTTP header from either httpx.Headers or a plain mapping."""

    lowered = name.lower()
    return next((value for key, value in headers.items() if key.lower() == lowered), "")


def _optional_bool(value: Any, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _optional_number(value: Any, field_name: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def analyze_probe_result(
    result: CaptivePortalProbeResult,
    *,
    notes: str | None = None,
) -> PortalReport:
    """Hand a validated portal URL to the existing passive analyzer."""

    from portallens.plugins.captive_wifi import CaptiveWifiPortal

    return CaptiveWifiPortal().analyze(result.analysis_context(notes=notes))


def _evidence(
    evidence_type: EvidenceType,
    profile: CaptivePortalProbeProfile,
    key: str,
    value: str,
    note: str,
) -> Evidence:
    return Evidence(
        type=evidence_type,
        source=f"wifi-probe://{profile.name}",
        key=key,
        value=value,
        note=note,
    )


__all__ = [
    "ANDROID_CLIENTS3_GENERATE_204",
    "ANDROID_GENERATE_204",
    "APPLE_HOTSPOT",
    "FIREFOX_CANONICAL",
    "GNOME_NETWORK_STATUS",
    "PROBE_PROFILES",
    "WINDOWS_CONNECT_TEST",
    "WINDOWS_NCSI",
    "CaptivePortalDetector",
    "CaptivePortalMetadata",
    "CaptivePortalProbeProfile",
    "CaptivePortalProbeResult",
    "CaptivePortalResponse",
    "WifiProbePlatform",
    "analyze_probe_result",
    "apply_probe_result",
    "parse_captive_portal_metadata",
    "profiles_for_platform",
]
