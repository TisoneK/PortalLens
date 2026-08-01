"""The :class:`Portal` abstraction — PortalLens's core extension point.

Every portal type (captive Wi-Fi, web auth, payment, ISP) is a subclass
of :class:`Portal`. Subclasses implement :meth:`analyze`, which receives
an :class:`AnalysisContext` (URLs + optional HTML/HAR payloads + an
acquisition policy) and returns a :class:`PortalReport` containing
evidence, observations, fingerprints, and inferred relationships.

The base class deliberately does not mandate how a portal acquires its
inputs. The default :class:`AcquisitionPolicy` is **passive** — analysis
works purely from URLs and user-supplied payloads. Active probing (HTTP
fetches, port scans, DNS lookups beyond URL parsing) requires the caller
to pass an ``AcquisitionPolicy`` with the relevant flags enabled, and
the caller is responsible for having authorization for the target.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from portallens.confidence import Confidence
from portallens.evidence import Evidence, Observation


class PortalType(str, Enum):
    """Broad category of portal. New types added as plugins land."""

    CAPTIVE_WIFI = "captive_wifi"
    WEB_AUTH = "web_auth"        # reserved — not implemented yet
    PAYMENT = "payment"          # reserved
    ISP = "isp"                  # reserved


class Severity(str, Enum):
    """Impact level of a security finding (ADR-11 disclosure schema)."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityFinding(BaseModel):
    """A single security finding — the disclosure record ADR-11 mandates.

    Every finding carries the disclosure schema from the user's preferences:
    Title, Affected asset, Evidence, Impact, Confidence, Recommended
    remediation, and Verification status. ``confidence`` uses the same
    ``[0, 100]`` rubric as every other PortalLens claim; ``verification_status``
    reflects whether the check's rule has been validated against a real
    capture (``Provenance``) or is provisional.
    """

    check_slug: str
    title: str
    severity: Severity
    confidence: int = Field(ge=0, le=100)
    affected: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    impact: str
    remediation: str
    verification_status: str
    note: str | None = None


class RelationshipKind(str, Enum):
    """How two portals / services relate to each other.

    The relationship model is intentionally permissive — a single
    observed redirect can imply multiple kinds (e.g. ``REDIRECTS_TO`` +
    ``USES_PLATFORM``). The relationship's confidence score reflects how
    strongly the evidence supports that specific kind.
    """

    REDIRECTS_TO = "redirects_to"                # one URL points at another
    USES_PLATFORM = "uses_platform"              # operator uses a 3rd-party platform as backend
    OPERATES_NETWORK = "operates_network"        # one entity operates the underlying network
    RESELLS_BANDWIDTH = "resells_bandwidth"      # one entity resells another's bandwidth
    UPSTREAM_OF = "upstream_of"                  # one entity is upstream ISP of another
    AUTHENTICATES_FOR = "authenticates_for"      # one portal handles auth for another
    SAME_OPERATOR = "same_operator"              # two portals operated by the same entity


@dataclass
class AcquisitionPolicy:
    """What an analyzer is allowed to do to gather evidence.

    Passive analysis (URL parsing, fingerprinting user-supplied HTML/HAR)
    is always allowed. Every active technique — fetching URLs, doing DNS
    lookups beyond the URL parser, port scanning, TLS probing — must be
    explicitly enabled here. **The caller is responsible for ensuring
    they have authorization for any active technique they enable.**
    """

    fetch_urls: bool = False
    follow_redirects: bool = False
    resolve_dns: bool = False
    probe_tls: bool = False
    port_scan: bool = False
    use_osint_apis: bool = False  # ADR-13 Tier-1: third-party OSINT (CT logs, ASN/RIPEstat) — leaves the machine, does NOT touch the target
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_passive(self) -> bool:
        """True iff no active technique is enabled.

        ADR-13 note: ``use_osint_apis`` touches third parties (leaves the
        machine) even though it never touches the target, so it is neither
        ``is_passive`` nor target-facing-active — it is its own middle tier.
        """

        return not any(
            (
                self.fetch_urls,
                self.follow_redirects,
                self.resolve_dns,
                self.probe_tls,
                self.port_scan,
                self.use_osint_apis,
            )
        )


@dataclass
class AnalysisContext:
    """Inputs handed to a :class:`Portal.analyze` call.

    ``urls`` is the only required field — the user pasted at least one
    portal URL. ``html_payloads`` maps a URL to the HTML the user
    captured (e.g. from browser DevTools) when they don't want the
    analyzer to fetch it. ``har_payloads`` is the same idea for HAR
    captures. ``policy`` controls what active techniques are allowed.
    """

    urls: list[str]
    html_payloads: dict[str, str] = field(default_factory=dict)
    har_payloads: dict[str, str] = field(default_factory=dict)
    policy: AcquisitionPolicy = field(default_factory=AcquisitionPolicy)
    user_notes: str | None = None


class PortalFingerprint(BaseModel):
    """A detected platform / technology fingerprint on a portal.

    A single portal can match multiple fingerprints (e.g. a MikroTik
    hotspot fronted by an ISPMan captive portal). Each carries its own
    confidence — the analyzer never collapses them into one.
    """

    platform: str
    version: str | None = None
    confidence: int = Field(ge=0, le=100)
    evidence_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class PortalRelationship(BaseModel):
    """An inferred relationship between this portal and another entity.

    ``other`` may be a domain, an IP, an ASN, an organization name, or
    another portal id. The ``kind`` and ``confidence`` together describe
    how strongly the evidence supports the relationship.
    """

    kind: RelationshipKind
    other: str
    confidence: int = Field(ge=0, le=100)
    evidence_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class OpenQuestion(BaseModel):
    """A gap the analyzer could not close, expressed as structured data.

    Before this, open questions were bare strings — prose at the bottom of a
    report. That made "what would resolve this?" a sentence a human had to
    write consistently, and made a graph view unable to lay the gap out.

    Now:

    - ``subject`` is the entity the question is about (a host, a platform).
    - ``question`` is the human-readable prompt.
    - ``kind`` is the relationship edge that would be established if the
      question were answered. Set it when the question maps to a specific
      missing relationship (``UPSTREAM_OF``, ``RESELLS_BANDWIDTH``, …) so a
      graph view can draw an explicit *unknown* edge rather than burying the
      gap in prose; leave it ``None`` for questions that refine an existing
      node rather than proposing an edge.
    - ``resolves_with`` names the analysis steps — by slug — that could answer
      the question. This is the basis for a *computed* "next investigation"
      queue (ADR-9): match a report's open questions against the registered
      steps that can answer them. An empty list means no automated step can
      resolve it (it needs manual field capture). The slugs are plain strings
      for now; the ``AnalysisStep`` registry that owns them is a later slice.
    """

    subject: str
    question: str
    kind: RelationshipKind | None = None
    resolves_with: list[str] = Field(default_factory=list)


class PortalReport(BaseModel):
    """The full output of a :class:`Portal.analyze` call.

    A report is immutable once produced. It carries:

    - ``evidence``: the raw, sourced observations.
    - ``observations``: facts, inferences, and hypotheses derived from evidence.
    - ``fingerprints``: detected platforms / technologies.
    - ``relationships``: inferred relationships to other entities.
    - ``open_questions``: things the analyzer couldn't resolve with the
      evidence available — explicit prompts for follow-up.
    """

    portal_type: PortalType
    primary_url: str
    evidence: list[Evidence] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    fingerprints: list[PortalFingerprint] = Field(default_factory=list)
    relationships: list[PortalRelationship] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    findings: list[SecurityFinding] = Field(default_factory=list)

    def evidence_by_id(self, evidence_id: str) -> Evidence | None:
        for ev in self.evidence:
            if ev.id == evidence_id:
                return ev
        return None

    def observations_of_kind(self, kind: str) -> list[Observation]:
        return [o for o in self.observations if o.kind == kind]

    def strongest_fingerprint(self) -> PortalFingerprint | None:
        if not self.fingerprints:
            return None
        return max(self.fingerprints, key=lambda f: f.confidence)

    def findings_for_check(self, check_slug: str) -> list[SecurityFinding]:
        return [f for f in self.findings if f.check_slug == check_slug]

    def summary_confidence(self, statement_substring: str) -> Confidence | None:
        """Return the highest confidence attached to any observation
        whose statement contains ``statement_substring`` (case-insensitive).

        Returns ``None`` if no observation matches. Useful for the
        reporting layer to extract a headline confidence ("how confident
        are we that ISPMan handles authentication?").
        """

        needle = statement_substring.lower()
        matches = [o for o in self.observations if needle in o.statement.lower()]
        if not matches:
            return None
        return Confidence(max(o.confidence for o in matches))


class Portal(ABC):
    """Abstract base — every portal type implements this.

    Subclasses set ``portal_type`` and implement :meth:`analyze`.
    Subclasses should be idempotent: given the same
    :class:`AnalysisContext`, they produce the same :class:`PortalReport`
    (modulo evidence id auto-increment, which tests reset via
    :func:`portallens.evidence.reset_evidence_ids`).
    """

    portal_type: PortalType

    @abstractmethod
    def analyze(self, context: AnalysisContext) -> PortalReport:
        """Run passive (and, if the policy allows, active) analysis on
        ``context`` and return an evidence-backed :class:`PortalReport`.

        Implementations MUST:

        - Record every raw input as :class:`Evidence` before deriving
          any :class:`Observation` from it.
        - Cite evidence ids in every non-fact observation.
        - Cap hypothesis confidence at 39 (``low``) by convention.
        - Populate ``open_questions`` for anything they couldn't
          resolve, rather than silently dropping it.
        """
        raise NotImplementedError

    @staticmethod
    def confidence(value: int) -> Confidence:
        """Convenience accessor — ``Portal.confidence(75)`` for
        ``Confidence(75)``. Saves an import in subclasses."""

        return Confidence(value)
