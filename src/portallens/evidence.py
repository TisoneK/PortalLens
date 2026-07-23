"""Evidence — atomic, sourced observations that back every inference.

PortalLens separates three kinds of statements in its reports:

- **Observed facts** — direct observations: a URL parameter was present,
  an HTTP header returned a specific value, a DNS record resolved. These
  live as :class:`Evidence` records.
- **Inferences** — conclusions drawn from one or more pieces of evidence,
  with a confidence score and the evidence they rest on. These are
  :class:`Observation` records with ``kind=INFERENCE``.
- **Hypotheses** — speculative explanations offered when evidence is
  thin, explicitly labelled so the reader knows they need verification.
  These are :class:`Observation` records with ``kind=HYPOTHESIS``.

Every :class:`Observation` of kind ``INFERENCE`` or ``HYPOTHESIS`` must
reference at least one :class:`Evidence` id, so a report reader can always
trace "why does this say 72%?" back to the raw inputs.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    """What kind of raw input an :class:`Evidence` record captures."""

    URL_PARAMETER = "url_parameter"        # a query-string key/value on a portal URL
    URL_PATH = "url_path"                   # a path segment on a portal URL
    URL_HOST = "url_host"                   # the hostname of a portal URL
    URL_REDIRECT = "url_redirect"           # an observed redirect from one URL to another
    HTTP_HEADER = "http_header"             # an HTTP response header value
    HTML_ELEMENT = "html_element"           # a DOM element / attribute observed in portal HTML
    JS_BUNDLE = "js_bundle"                 # a JavaScript asset URL or hash
    DNS_RECORD = "dns_record"               # a resolved DNS record (A, AAAA, CNAME, TXT, …)
    TLS_CERTIFICATE = "tls_certificate"     # a TLS certificate SAN / issuer / subject field
    IP_ASN = "ip_asn"                       # IP ownership / ASN data
    USER_SUPPLIED = "user_supplied"         # the user pasted this in directly


class Evidence(BaseModel):
    """A single, sourced observation.

    Attributes
    ----------
    id:
        Stable identifier used by :class:`Observation.evidence_ids` to
        reference this record. Auto-generated as ``e{N}`` if omitted.
    type:
        What kind of observation this is (see :class:`EvidenceType`).
    source:
        Where it came from — a URL, a filename, ``user`` for chat input,
        etc. Never a secret value.
    key:
        What was observed — e.g. the URL parameter name, the HTTP header
        name, the DNS record type.
    value:
        The observed value, redacted if it could carry user data.
    note:
        Optional human-readable context.
    """

    id: str = Field(default_factory=lambda: _next_evidence_id())
    type: EvidenceType
    source: str
    key: str
    value: str
    note: str | None = None


_observation_kind = Literal["fact", "inference", "hypothesis"]


class Observation(BaseModel):
    """A statement about the portal — fact, inference, or hypothesis.

    ``kind=fact`` observations are restatements of one or more
    :class:`Evidence` records. ``kind=inference`` observations are
    conclusions drawn from evidence with a confidence score.
    ``kind=hypothesis`` observations are speculative explanations
    explicitly flagged for verification — confidence is capped at ``low``
    by convention.
    """

    kind: _observation_kind
    statement: str
    confidence: int = Field(ge=0, le=100)
    evidence_ids: list[str] = Field(default_factory=list)
    note: str | None = None


_evidence_counter = 0


def _next_evidence_id() -> str:
    global _evidence_counter
    _evidence_counter += 1
    return f"e{_evidence_counter}"


def reset_evidence_ids() -> None:
    """Reset the auto-incrementing evidence id counter.

    Useful in tests to make evidence ids deterministic across runs.
    Never call this in production code — ids are meant to be unique
    within a single :class:`PortalReport`.
    """

    global _evidence_counter
    _evidence_counter = 0
