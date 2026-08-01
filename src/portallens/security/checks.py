"""The SecurityCheck registry — security checks as data (ADR-11).

Security checks are keyed on the **evidence they require**, not on the
vendor. A check declares an :class:`EvidenceRequirement` — the kinds of
evidence that make the condition detectable — and produces a
:class:`SecurityFinding` with the disclosure schema (Title, Affected asset,
Evidence, Impact, Confidence, Recommended remediation, Verification status)
when enough matching evidence exists.

Why evidence-keyed rather than vendor-keyed: a check that silently runs
against only one provider is a false sense of coverage, which in a security
tool is a defect, not just untidy. Checks run against whatever evidence an
investigation holds, regardless of vendor.

Provenance (ADR-6) applies: a check derived from a CVE or writeup not
reproduced in-repo is ``DOCUMENTED``, not ``VALIDATED``, and its findings
say so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from portallens.confidence import Confidence, score
from portallens.evidence import Evidence, EvidenceType
from portallens.portal import SecurityFinding, Severity
from portallens.provenance import Provenance


@dataclass(frozen=True)
class EvidenceRequirement:
    """A predicate over evidence records — what a check needs to fire.

    All constraints are conjunctive: a record must satisfy every non-empty
    constraint to count. ``min_matches`` is how many matching records the
    check needs before it fires.
    """

    types: tuple[EvidenceType, ...] = ()
    key_prefixes: tuple[str, ...] = ()
    keys: tuple[str, ...] = ()
    value_contains: tuple[str, ...] = ()
    min_matches: int = 1

    def matches(self, ev: Evidence) -> bool:
        return not (
            (self.types and ev.type not in self.types)
            or (self.key_prefixes and not any(ev.key.startswith(p) for p in self.key_prefixes))
            or (self.keys and ev.key not in self.keys)
            or (
                self.value_contains
                and not any(needle.lower() in ev.value.lower() for needle in self.value_contains)
            )
        )


@dataclass(frozen=True)
class SecurityCheck:
    """One registered security check — the registry entry.

    ``requires`` is the evidence predicate. ``confidence_weights`` maps an
    evidence key (or key prefix match) to a weight fed into the noisy-OR
    ``score()`` rule; ``base_confidence`` is the floor used when a check
    fires on qualifying evidence that carries no specific weight.
    ``verification_status`` is derived from ``provenance``: a DOCUMENTED
    check is reported as provisional.
    """

    slug: str
    title: str
    severity: Severity
    impact: str
    remediation: str
    requires: EvidenceRequirement
    provenance: Provenance = Provenance.DOCUMENTED
    confidence_weights: dict[str, int] = field(default_factory=dict)
    base_confidence: int = 70


# ---------------------------------------------------------------------------
# The registry — the only file that names a check's specifics.
# ---------------------------------------------------------------------------

CLIENT_FINGERPRINTING = SecurityCheck(
    slug="client_fingerprinting_preauth",
    title="Portal collects device-fingerprinting parameters before authentication",
    severity=Severity.LOW,
    impact=(
        "The portal collects device-identifying parameters (canvas fingerprint, "
        "WebGL, user agent, timezone, screen size, cookie) before the user "
        "authenticates. This data can be used to fingerprint and track the "
        "device across sessions, and is collected without the user having "
        "consented to authentication."
    ),
    remediation=(
        "Collect only the parameters authentication actually requires, and do "
        "so only after the user has accepted the portal's privacy terms. "
        "Avoid persistent canvas/WebGL fingerprinting of unauthenticated users."
    ),
    provenance=Provenance.VALIDATED,  # the ISPMAN fixture carries the full fingerprint set
    requires=EvidenceRequirement(
        types=(EvidenceType.URL_PARAMETER,),
        keys=(
            "canvasFingerprint",
            "webgl",
            "userAgent",
            "timezone",
            "cookie",
            "height",
            "width",
            "platform",
        ),
        min_matches=1,
    ),
    confidence_weights={
        "canvasFingerprint": 90,
        "webgl": 80,
        "userAgent": 55,
        "timezone": 50,
        "cookie": 60,
        "height": 40,
        "width": 40,
        "platform": 40,
    },
)

CLEARTEXT_LOGIN = SecurityCheck(
    slug="cleartext_login_form",
    title="Login form submits credentials over cleartext HTTP",
    severity=Severity.HIGH,
    impact=(
        "The portal's authentication form posts over unencrypted HTTP. "
        "Credentials and the session are visible to anyone on the network "
        "path — including, in a captive-portal deployment, the operator's "
        "own gateway."
    ),
    remediation="Serve the login form over HTTPS and enforce HTTPS for the form action.",
    provenance=Provenance.DOCUMENTED,
    requires=EvidenceRequirement(
        types=(EvidenceType.HTML_ELEMENT,),
        value_contains=("action=\"http://", "action='http://"),
        min_matches=1,
    ),
)

GATEWAY_ADMIN_EXPOSED = SecurityCheck(
    slug="gateway_admin_exposed",
    title="Gateway administrative interface reachable from the client network",
    severity=Severity.HIGH,
    impact=(
        "An administrative port on the gateway is reachable from the client "
        "network. If an admin interface is exposed, a network attacker can "
        "attempt to access it — a common misconfiguration with severe "
        "consequences for the operator."
    ),
    remediation=(
        "Restrict administrative ports to a management VLAN or trusted source "
        "addresses; disable admin services on client-facing interfaces."
    ),
    provenance=Provenance.DOCUMENTED,
    requires=EvidenceRequirement(
        types=(EvidenceType.SERVICE_REACHABLE,),
        key_prefixes=("admin_port:",),
        min_matches=1,
    ),
    confidence_weights={
        "admin_port:8291": 95,  # MikroTik WebFig
        "admin_port:8728": 90,  # MikroTik API
        "admin_port:8729": 90,  # MikroTik API (TLS)
        "admin_port:22": 60,    # SSH — ambiguous, could be legit
        "admin_port:23": 65,    # Telnet — legacy, likely admin
    },
)


CHECKS: tuple[SecurityCheck, ...] = (
    CLIENT_FINGERPRINTING,
    CLEARTEXT_LOGIN,
    GATEWAY_ADMIN_EXPOSED,
)


def check_for_slug(slug: str) -> SecurityCheck | None:
    """Look a check up by its slug."""

    return next((c for c in CHECKS if c.slug == slug), None)


def run_checks(evidence: list[Evidence]) -> list[SecurityFinding]:
    """Run every registered check against ``evidence``.

    Returns findings sorted by confidence, highest first. A check fires when
    at least ``requires.min_matches`` evidence records satisfy its
    requirement; confidence combines per-key weights via the noisy-OR
    ``score()`` rule (or the check's ``base_confidence`` when no weight
    matches). DOCUMENTED-provenance checks are marked provisional.
    """

    findings: list[SecurityFinding] = []
    for check in CHECKS:
        matches = [ev for ev in evidence if check.requires.matches(ev)]
        if len(matches) < check.requires.min_matches:
            continue
        weights = [
            check.confidence_weights[ev.key]
            for ev in matches
            if ev.key in check.confidence_weights
        ]
        conf = score(weights) if weights else Confidence(check.base_confidence)
        verified = check.provenance is Provenance.VALIDATED
        findings.append(
            SecurityFinding(
                check_slug=check.slug,
                title=check.title,
                severity=check.severity,
                confidence=conf.value,
                affected=_affected_asset(matches),
                evidence_ids=[ev.id for ev in matches],
                impact=check.impact,
                remediation=check.remediation,
                verification_status=(
                    "validated against a captured URL in this repo's fixtures"
                    if verified
                    else "provisional — check derived from documentation, not yet validated"
                ),
            )
        )
    findings.sort(key=lambda f: -f.confidence)
    return findings


def _affected_asset(matches: list[Evidence]) -> str | None:
    """The host most of the matching evidence points at, if any."""

    for ev in matches:
        if ev.type is EvidenceType.URL_HOST:
            return ev.value
    # Fall back to the source URL's hostname.
    for ev in matches:
        host = urlparse(ev.source).hostname
        if host:
            return host
    return None
