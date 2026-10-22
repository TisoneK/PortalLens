"""Skin-agnostic reading of a hotspot session view.

Every gateway renders the same facts — session username, plan, time left,
bytes left — in whatever markup its operator's skin uses: RouterOS tables,
billing-provider tables with ``<th>`` labels, Bootstrap cards, definition
lists, bare divs. Teaching a parser one skin at a time makes every
unfamiliar portal read as "no session held", which is the one wrong answer
that looks like evidence.

So this module reads *structure*, not class names: the page is flattened to
an ordered list of text runs with their element paths, and a run that reads
like a label is paired with the run that follows it inside the same
container. Labels are then mapped onto canonical session fields by meaning
(and, where the wording is ambiguous, by the shape of the value — a
duration is a time-left, a timestamp is an expiry). Labels that look like
labels but map to nothing are returned as :attr:`SessionView.unmapped`, so
the caller can say "the view was found but not understood" instead of
"there was no view".

Nothing here fetches anything: this is pure parsing, applied to a body the
caller already obtained under an authorization decision (ADR-28).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

#: Canonical session fields, in the order the stock template lists them.
CANONICAL_FIELDS = (
    "USERNAME",
    "MAC",
    "IP",
    "PLAN",
    "START-TIME",
    "SESSION-LEFT",
    "EXPIRES-ON",
    "BYTES LEFT",
)

#: Elements whose text is never part of the visible session view.
_SKIP_ELEMENTS = frozenset({"head", "script", "style", "title", "textarea", "noscript"})

#: Elements with no closing tag, so they must not open a container.
_VOID_ELEMENTS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
)

_DURATION = re.compile(
    r"^(?:\d+\s*(?:d|h|m|s|days?|hrs?|hours?|mins?|minutes?|secs?|seconds?)\s*)+$"
    r"|^\d{1,3}:\d{2}(?::\d{2})?$",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
    re.IGNORECASE,
)
_DATA = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:b|bytes?|kb|mb|gb|tb|kib|mib|gib|kilobytes?|megabytes?|gigabytes?)$",
    re.IGNORECASE,
)
_UNLIMITED = re.compile(r"^(?:unlimited|infinite|none|n/?a|∞|-+)$", re.IGNORECASE)
_MONEY = re.compile(r"^(?:kes|kshs?|usd|eur|gbp|\$|€|£)\b|/=\s*$", re.IGNORECASE)
_MAC = re.compile(r"^(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}$", re.IGNORECASE)
_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")

#: Unmapped pairs kept per scan — enough to teach a new skin, not a page dump.
_UNMAPPED_CAP = 8
_UNMAPPED_VALUE_CAP = 40


@dataclass(frozen=True)
class LabelValue:
    """One label/value pair read off the page, before field mapping."""

    label: str
    value: str | None


@dataclass(frozen=True)
class SessionView:
    """What the structural reader found, including what it could not name."""

    fields: dict[str, str | None] = field(default_factory=dict)
    pairs_read: int = 0
    unmapped: tuple[LabelValue, ...] = ()

    @property
    def found(self) -> bool:
        """Whether the page rendered at least one label/value pair."""

        return self.pairs_read > 0


@dataclass(frozen=True)
class _Run:
    """One contiguous piece of visible text, with its element path."""

    text: str
    path: tuple[int, ...]

    @property
    def parent(self) -> int:
        return self.path[-1] if self.path else 0


class _RunCollector(HTMLParser):
    """Flatten markup to ordered text runs carrying their element paths."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.runs: list[_Run] = []
        self._path: list[int] = []
        self._next_id = 1
        self._skip_tag: str | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._skip_depth:
            if tag == self._skip_tag and tag not in _VOID_ELEMENTS:
                self._skip_depth += 1
            return
        if tag in _SKIP_ELEMENTS:
            self._skip_tag = tag
            self._skip_depth = 1
            return
        if tag in _VOID_ELEMENTS:
            return
        self._path.append(self._next_id)
        self._next_id += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Self-closing: neither opens nor closes a container.
        return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth -= 1
                if self._skip_depth == 0:
                    self._skip_tag = None
            return
        if tag in _VOID_ELEMENTS:
            return
        if self._path:
            self._path.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if text:
            self.runs.append(_Run(text=text, path=tuple(self._path)))


def read_session_view(html: str) -> SessionView:
    """Read the session view out of markup of any shape."""

    return session_view_from_runs(_collect_runs(html))


def session_view_from_runs(runs: list[_Run]) -> SessionView:
    """Pair label/value runs and map the labels onto canonical fields."""

    fields: dict[str, str | None] = {}
    soft_empty: dict[str, None] = {}
    unmapped: list[LabelValue] = []
    pairs = 0
    index = 0
    while index < len(runs):
        run = runs[index]
        if not _labelish(run.text):
            index += 1
            continue
        follower = runs[index + 1] if index + 1 < len(runs) else None
        if follower is None or not _adjacent(run, follower):
            index += 1
            continue

        if _is_label(follower.text):
            # An empty cell: the label is followed by the next label, the
            # shape a profile-less session produces for PLAN/START-TIME.
            # Recorded softly, so a real value later on the page wins.
            field = canonical_field(run.text)
            if field is not None:
                soft_empty.setdefault(field, None)
            pairs += 1
            index += 1
            continue

        value_parts = [follower.text]
        cursor = index + 2
        while (
            cursor < len(runs)
            and runs[cursor].parent == follower.parent
            and not _is_label(runs[cursor].text)
            and _adjacent(follower, runs[cursor])
        ):
            value_parts.append(runs[cursor].text)
            cursor += 1
        value = " ".join(value_parts).strip() or None

        pairs += 1
        field = canonical_field(run.text, value)
        if field is None:
            if value is not None and len(unmapped) < _UNMAPPED_CAP:
                unmapped.append(LabelValue(run.text, _clip(value)))
        elif field not in fields:
            fields[field] = value
        index = cursor

    for field, empty in soft_empty.items():
        fields.setdefault(field, empty)
    return SessionView(fields=fields, pairs_read=pairs, unmapped=tuple(unmapped))


def canonical_field(label: str, value: str | None = None) -> str | None:
    """Map a skin's label onto a canonical field, by wording then by value shape.

    Returning ``None`` is the honest answer for a label this reader does not
    understand: the caller reports it rather than guessing, so an unrelated
    card — an amount paid, a phone number — can never populate a field.
    """

    norm = _normalise(label)
    if not norm:
        return None
    tokens = set(re.split(r"[\s/:_().-]+", norm))
    tokens.discard("")

    if "username" in norm or "user name" in norm or "subscriber" in norm:
        return "USERNAME"
    if "mac" in tokens or "macaddress" in norm:
        return "MAC"
    if "ip address" in norm or "ipaddress" in norm or norm == "ip":
        return "IP"
    # Expiry wording is tested before the plan wording: "Bundle will expire
    # in" names a bundle, but the fact it carries is time left, not a plan.
    if "expir" in norm or "valid until" in norm or "validity" in norm:
        return _expiry_field(norm, tokens, value)
    if tokens & {"plan", "package", "profile", "subscription", "bundle"}:
        return "PLAN"
    if "start" in tokens and tokens & {"time", "at", "date"}:
        return "START-TIME"
    if tokens & {"left", "remaining"} and tokens & {"time", "session", "duration"}:
        return "SESSION-LEFT"
    if tokens & {"bytes", "data", "quota", "volume"} or "balanc" in norm:
        if value is not None and (_MONEY.search(value.strip()) or _is_pair_value(value)):
            return None
        return "BYTES LEFT"
    # Wording this reader does not know, but the value's shape may be
    # unambiguous enough to carry the field on its own.
    if (
        value is not None
        and _DURATION.match(value.strip())
        and tokens & {"limit", "allowance"}
    ):
        return "SESSION-LEFT"
    return None


def _expiry_field(norm: str, tokens: set[str], value: str | None) -> str | None:
    """Split the expiry wording into "time left" versus "expires on"."""

    if tokens & {"left", "remaining"} or re.search(r"\bexpire[sd]? (?:in|after)\b", norm):
        return "SESSION-LEFT"
    if tokens & {"on", "at", "date", "until"}:
        return "EXPIRES-ON"
    if value is not None:
        stripped = value.strip()
        if _DURATION.match(stripped):
            return "SESSION-LEFT"
        if _DATE.search(stripped):
            return "EXPIRES-ON"
    return "EXPIRES-ON"


def _collect_runs(html: str) -> list[_Run]:
    collector = _RunCollector()
    collector.feed(html)
    collector.close()
    return collector.runs


def _normalise(label: str) -> str:
    """Lowercase, collapse whitespace, and drop a trailing colon."""

    return re.sub(r"\s+", " ", label).strip().rstrip(":").strip().lower()


def _labelish(text: str) -> bool:
    """Whether a run could be a label rather than prose or a value."""

    stripped = text.strip()
    if not stripped or len(stripped) > 48:
        return False
    if any(mark in stripped for mark in ".!?"):
        return False
    return len(stripped.split()) <= 6


def _is_label(text: str) -> bool:
    """Whether a run reads as a label this reader recognises."""

    return canonical_field(text) is not None


def _adjacent(label: _Run, value: _Run) -> bool:
    """Whether two runs are label and value of the same view item.

    They must share a container one level above the deeper of the two: a
    label inside a card and the value beside it share the card, while a
    value from one card and a label from the next share only the page and
    are therefore not a pair.
    """

    common = 0
    for left, right in zip(label.path, value.path, strict=False):
        if left != right:
            break
        common += 1
    return common > 0 and common >= min(len(label.path), len(value.path)) - 1


def _is_pair_value(value: str) -> bool:
    """Whether a cell holds two quantities ("up / down") rather than one."""

    stripped = value.strip()
    if _DATE.search(stripped):
        return False
    parts = [part.strip() for part in stripped.split("/")]
    return len(parts) == 2 and all(parts)


def _clip(value: str) -> str:
    return value if len(value) <= _UNMAPPED_VALUE_CAP else value[:_UNMAPPED_VALUE_CAP] + "..."


__all__ = [
    "CANONICAL_FIELDS",
    "LabelValue",
    "SessionView",
    "canonical_field",
    "read_session_view",
]
