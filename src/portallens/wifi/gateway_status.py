"""MikroTik hotspot gateway status — the session view the gateway itself holds.

The hotspot ``/status`` page renders the *gateway's* belief about the current
session: the hotspot username, the device MAC/IP, the attached plan, and the
remaining time/byte limits. Reading it answers the question a connectivity
probe cannot — *why* is this device authorized — but it is a request to the
gateway, and on some installations an unauthenticated portal request can
reset the session. The watch therefore never fetches this page on its own
initiative: the CLI fetches it only behind ``--authorized``, bracketed by two
connectivity probes that detect a perturbation (ADR-28). This module holds
the parsing and the bounded fetch; policy stays with the caller.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from portallens.acquisition.fetcher import FetchedDocument
from portallens.acquisition.fetcher import fetch as _http_fetch
from portallens.portal import AcquisitionPolicy

#: Labels of the MikroTik hotspot status template, in page order. "BYTES LEFT"
#: is the only multi-word label; the parser joins it while tokenizing.
_STATUS_LABELS = frozenset(
    {"USERNAME", "MAC", "IP", "PLAN", "START-TIME", "SESSION-LEFT", "EXPIRES-ON", "BYTES LEFT"}
)

_NOT_ASSIGNED = "not assigned"


@dataclass(frozen=True)
class GatewaySessionInfo:
    """The parsed session view, with empty template cells as None."""

    username: str | None
    mac: str | None
    ip: str | None
    plan: str | None
    start_time: str | None
    session_left: str | None
    expires_on: str | None
    bytes_left: str | None
    source_url: str

    @property
    def active(self) -> bool:
        """A rendered username means the gateway holds a session for this device."""

        return self.username is not None

    @property
    def limits_unassigned(self) -> bool:
        """All three limit cells read "Not assigned" — no time or byte caps."""

        cells = (self.session_left, self.expires_on, self.bytes_left)
        return all(c is not None and _NOT_ASSIGNED in c.lower() for c in cells)


FetchFn = Callable[[str, AcquisitionPolicy], FetchedDocument]


def status_url_for_gateway(gateway_ipv4: str) -> str:
    """The hotspot status page for a gateway address."""

    return f"http://{gateway_ipv4}/status"


def parse_mikrotik_status(text: str, *, source_url: str = "") -> GatewaySessionInfo:
    """Parse the MikroTik hotspot status template from HTML or flattened text.

    The served page is a label/value table — row cells are read
    structurally so prose outside the table (footnote markers, links)
    cannot bleed into a value. A copy-pasted rendering of the page (no
    tags) is tokenized instead: known labels anchor the scan and a label
    followed immediately by another label has an empty value, the shape a
    profile-less session produces for PLAN/START-TIME.
    """

    looks_like_html = "<" in text and ">" in text
    values = _parse_status_rows(text) if looks_like_html else _parse_status_tokens(text)

    return GatewaySessionInfo(
        username=values.get("USERNAME"),
        mac=(values.get("MAC") or "").upper() or None,
        ip=values.get("IP"),
        plan=values.get("PLAN"),
        start_time=values.get("START-TIME"),
        session_left=values.get("SESSION-LEFT"),
        expires_on=values.get("EXPIRES-ON"),
        bytes_left=values.get("BYTES LEFT"),
        source_url=source_url,
    )


def _parse_status_rows(html: str) -> dict[str, str | None]:
    """Read label/value pairs out of the status table's two-cell rows."""

    values: dict[str, str | None] = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) != 2:
            continue
        label = re.sub(r"<[^>]+>", "", cells[0]).strip().upper()
        if label not in _STATUS_LABELS:
            continue
        value = re.sub(r"<[^>]+>", "", cells[1]).strip()
        values[label] = value if value else None
    return values


def _parse_status_tokens(text: str) -> dict[str, str | None]:
    """Tokenize a tag-less rendering of the status page."""

    tokens = text.split()
    values: dict[str, str | None] = {}
    index = 0
    while index < len(tokens):
        label = _label_at(tokens, index)
        if label is None:
            index += 1
            continue
        index += 2 if label == "BYTES LEFT" else 1
        captured: list[str] = []
        while index < len(tokens) and _label_at(tokens, index) is None:
            captured.append(tokens[index])
            index += 1
        value = " ".join(captured).strip()
        values[label] = value if value else None
    return values


def _label_at(tokens: list[str], index: int) -> str | None:
    token = tokens[index].upper()
    if token == "BYTES" and index + 1 < len(tokens) and tokens[index + 1].upper() == "LEFT":
        return "BYTES LEFT"
    if token in _STATUS_LABELS:
        return token
    return None


def fetch_gateway_session(
    url: str,
    policy: AcquisitionPolicy,
    *,
    fetch: FetchFn = _http_fetch,
) -> GatewaySessionInfo:
    """Fetch and parse the status page under the given policy (ADR-15).

    Raises :class:`~portallens.acquisition.AcquisitionDenied` without
    ``policy.authorized`` — the caller owns the authorization decision.
    """

    document = fetch(url, policy)
    return parse_mikrotik_status(document.body, source_url=document.final_url)


#: Mobile-money transaction codes (M-Pesa and similar integrations) are
#: 10-character uppercase alphanumerics; hotspot billing integrations that
#: name the session user after the payment produce usernames in this shape.
PAYMENT_CODE_PATTERN = re.compile(r"^[A-Z0-9]{10}$")


def matches_payment_code_shape(username: str | None) -> bool:
    """Whether the username has a payment-transaction-code shape (format inference)."""

    if not username:
        return False
    return PAYMENT_CODE_PATTERN.fullmatch(username) is not None


__all__ = [
    "PAYMENT_CODE_PATTERN",
    "FetchFn",
    "GatewaySessionInfo",
    "fetch_gateway_session",
    "matches_payment_code_shape",
    "parse_mikrotik_status",
    "status_url_for_gateway",
]
