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
    uncertainty: str | None = None


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


GATEWAY_DEFAULT_CREDENTIAL = SecurityCheck(
    slug="gateway_admin_default_credential",
    title="Gateway administrative login accepts a well-known default credential",
    severity=Severity.CRITICAL,
    impact=(
        "An administrative service on the gateway accepted a published vendor "
        "default login from the client network. Anyone on the network can log "
        "in as administrator, change hotspot and firewall configuration, read "
        "session and billing records, and monitor or redirect client traffic."
    ),
    remediation=(
        "Set a unique administrative password, disable Telnet on the "
        "client-facing interface, and restrict administrative services to a "
        "management VLAN or trusted source addresses."
    ),
    provenance=Provenance.DOCUMENTED,
    requires=EvidenceRequirement(
        types=(EvidenceType.SERVICE_REACHABLE,),
        key_prefixes=("admin_credential:",),
        value_contains=("default_accepted",),
        min_matches=1,
    ),
    confidence_weights={"admin_credential:23": 95},
    base_confidence=90,
)


POST_EXPIRY_ACCESS = SecurityCheck(
    slug="post_expiry_access",
    title="Internet access available after recorded package expiry",
    severity=Severity.MEDIUM,
    impact=(
        "A connectivity probe verified unrestricted internet access at a time "
        "after the recorded package expiry, with no recorded renewal before "
        "the sample. On a paid hotspot this means session/billing enforcement "
        "is not terminating access - e.g. an expired session left active, "
        "MAC-cookie re-authorization, a free-access or grace profile, or a "
        "billing-to-router synchronization failure. The operator loses revenue "
        "and carries abuse surface while this persists."
    ),
    remediation=(
        "On the gateway, invalidate expired hotspot sessions and verify "
        "MAC-cookie, trial, and free-access profiles are not restoring "
        "expired accounts; on the billing side, verify expiry is pushed to "
        "the router and confirmed in the active-session table."
    ),
    provenance=Provenance.DOCUMENTED,
    requires=EvidenceRequirement(
        types=(EvidenceType.CAPTIVE_PORTAL_STATUS,),
        keys=("watch:post-expiry-access",),
        min_matches=1,
    ),
    confidence_weights={"watch:post-expiry-access": 80},
    base_confidence=70,
)


PORTAL_CLAIM_MISMATCH = SecurityCheck(
    slug="portal_claim_mismatch",
    title="Portal shows no package while internet access is verified",
    severity=Severity.MEDIUM,
    impact=(
        "At the same moment, a connectivity probe verified unrestricted internet "
        "access and the portal told the user to buy a package (or log in). The "
        "portal's view of the account and the gateway's authorization disagree, "
        "so the user is being asked to pay for access they already have - and an "
        "account with no valid package can still be passing traffic. Typical "
        "causes are a portal session lookup that does not match the gateway's "
        "active sessions (MAC cookie, ip-binding, or an accounting record the "
        "portal cannot see), or an unauthenticated portal request from behind a "
        "shared/NATed connection resetting the visible session while the "
        "authorization survives."
    ),
    remediation=(
        "Reconcile the portal's session lookup with the gateway's active-session "
        "and accounting tables for the same MAC and IP; decide whether an "
        "unauthenticated portal request from a NATed device should invalidate an "
        "existing session (usually it should not); and verify that a device "
        "holding no package never appears in the active-session table."
    ),
    provenance=Provenance.DOCUMENTED,
    requires=EvidenceRequirement(
        types=(EvidenceType.CAPTIVE_PORTAL_STATUS,),
        keys=("watch:portal-claim-mismatch",),
        min_matches=1,
    ),
    confidence_weights={"watch:portal-claim-mismatch": 78},
    base_confidence=72,
)


GATEWAY_SESSION_WITHOUT_PLAN = SecurityCheck(
    slug="gateway_session_without_plan",
    title="Gateway hotspot session active with no plan or limits attached",
    severity=Severity.MEDIUM,
    impact=(
        "The gateway's own hotspot status page shows an active session for "
        "this device with no plan attached and every time/byte limit 'Not "
        "assigned'. Traffic is authorized with no purchased package enforcing "
        "an end — the session persists until the gateway drops it. On a paid "
        "hotspot this usually means the billing integration created the "
        "session without applying the purchased profile, or granted a "
        "profile-less session directly."
    ),
    uncertainty=(
        "'Not assigned' is the status page's own wording, footnoted with an "
        "asterisk: it may mean no cap is enforced, or that this page does "
        "not populate caps. What the gateway actually enforces is not "
        "directly observable from the page."
    ),
    remediation=(
        "On the gateway, inspect the hotspot user behind the active session: "
        "attach the correct profile or drop the session so re-authorization "
        "requires a valid package. On the billing side, verify a payment "
        "always maps to a profiled hotspot user and that profile changes "
        "reach the router's active-session table."
    ),
    provenance=Provenance.DOCUMENTED,
    requires=EvidenceRequirement(
        types=(EvidenceType.CAPTIVE_PORTAL_STATUS,),
        keys=("watch:gateway-session-no-plan",),
        min_matches=1,
    ),
    confidence_weights={"watch:gateway-session-no-plan": 85},
    base_confidence=75,
)


SESSION_USERNAME_PAYMENT_CODE = SecurityCheck(
    slug="session_username_payment_code_shape",
    title="Hotspot session username matches a payment-transaction code format",
    severity=Severity.LOW,
    impact=(
        "The hotspot session username has the shape of a mobile-money "
        "transaction code (10 uppercase alphanumerics, e.g. an M-Pesa "
        "receipt code). Billing integrations that name the hotspot user "
        "after the payment tend to carry the code forever — the receipt is "
        "not a package, so nothing about it expires, and the enforcement "
        "question shifts entirely to whether a profile with limits was "
        "attached. This is a format inference, not a billing lookup."
    ),
    uncertainty=(
        "The shape alone cannot say whose code it is, which billing system "
        "issued it, or that it is a payment code at all — many unrelated "
        "strings match. Only the operator's own records can tie the "
        "username to a specific transaction."
    ),
    remediation=(
        "No gateway action is implied by the format alone. If the finding "
        "appears together with 'gateway_session_without_plan', treat the "
        "session as a payment artifact that outlived its package and audit "
        "the billing integration's user provisioning."
    ),
    provenance=Provenance.DOCUMENTED,
    requires=EvidenceRequirement(
        types=(EvidenceType.CAPTIVE_PORTAL_STATUS,),
        keys=("watch:gateway-session-username-payment-code-shape",),
        min_matches=1,
    ),
    confidence_weights={"watch:gateway-session-username-payment-code-shape": 55},
    base_confidence=45,
)


CHECKS: tuple[SecurityCheck, ...] = (
    CLIENT_FINGERPRINTING,
    CLEARTEXT_LOGIN,
    GATEWAY_ADMIN_EXPOSED,
    GATEWAY_DEFAULT_CREDENTIAL,
    GATEWAY_SESSION_WITHOUT_PLAN,
    PORTAL_CLAIM_MISMATCH,
    POST_EXPIRY_ACCESS,
    SESSION_USERNAME_PAYMENT_CODE,
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
                uncertainty=check.uncertainty,
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
