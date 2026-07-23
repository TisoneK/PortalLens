"""Acquisition — gather raw inputs for analysis.

The acquisition layer is the ONLY place PortalLens reaches outside the
process (HTTP fetches, DNS lookups, etc.). Every function here checks
the active :class:`AcquisitionPolicy` before doing anything active, and
raises :class:`AcquisitionDenied` if the policy forbids it.

Passive acquisition (URL parsing, working with user-supplied payloads)
has no policy gate — it's always allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlparse

from portallens.portal import AcquisitionPolicy


class AcquisitionDenied(Exception):
    """Raised when an active technique is requested but the policy
    doesn't allow it. Callers should treat this as a hard stop, not a
    retry — the user explicitly did not authorize the technique."""


@dataclass(frozen=True)
class ParsedPortalURL:
    """A passive parse of a portal URL.

    All fields are derived purely from :func:`urllib.parse.urlparse` —
    no network access. The analyzer uses this to extract evidence
    (hostname, path, query parameters) before deciding whether any
    active technique is needed.
    """

    raw: str
    scheme: str
    host: str
    port: int | None
    path: str
    query_params: list[tuple[str, str]]

    @classmethod
    def parse(cls, url: str) -> ParsedPortalURL:
        parsed = urlparse(url)
        # urlparse leaves the port inside .netloc or .hostname depending on form;
        # .hostname handles both, and .port raises ValueError on invalid ports.
        port: int | None = None
        try:
            port = parsed.port
        except ValueError:
            port = None
        return cls(
            raw=url,
            scheme=parsed.scheme or "",
            host=parsed.hostname or "",
            port=port,
            path=parsed.path or "",
            query_params=list(parse_qsl(parsed.query, keep_blank_values=True)),
        )

    def param(self, key: str) -> str | None:
        """First value for ``key`` in the query string, or ``None``."""

        for k, v in self.query_params:
            if k == key:
                return v
        return None

    def param_all(self, key: str) -> list[str]:
        """All values for ``key`` in the query string."""

        return [v for k, v in self.query_params if k == key]


def parse_portal_url(url: str) -> ParsedPortalURL:
    """Passive URL parse — always allowed, never reaches the network."""

    return ParsedPortalURL.parse(url)


def assert_policy(policy: AcquisitionPolicy, technique: str) -> None:
    """Gate an active technique against the policy.

    ``technique`` is the name of the :class:`AcquisitionPolicy` field
    the technique corresponds to (``"fetch_urls"``, ``"resolve_dns"``,
    etc.). Raises :class:`AcquisitionDenied` if the policy does not
    enable it.
    """

    if not getattr(policy, technique, False):
        raise AcquisitionDenied(
            f"technique {technique!r} is not enabled by the current AcquisitionPolicy. "
            f"Pass AcquisitionPolicy({technique}=True) — and ensure you have "
            f"authorization for the target before doing so."
        )
