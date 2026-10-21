"""Credential-free connectivity watch for session-enforcement observation.

This module answers one question: *does this network keep giving internet
access after it should have stopped?* The canonical scenario is a paid
hotspot package that expires — access stops, the customer reconnects, and
access returns without a new payment. Detecting that requires comparing
connectivity state **across time and across reconnects**, which a single
:class:`~portallens.wifi.captive_portal.CaptivePortalProbeResult` cannot do.

The watch is a passive accumulator:

- The caller runs the existing bounded, allow-listed connectivity probes
  (no new network behavior) and feeds each result to :meth:`ConnectivityWatch.record`.
- :meth:`ConnectivityWatch.begin_epoch` marks a (re)connection episode, so a
  reconnect can be compared against the state the previous epoch ended in.
- :meth:`ConnectivityWatch.add_boundary` records billing milestones the only
  way a read-only tool honestly can — from the user. PortalLens cannot
  observe billing state; the boundaries are user-supplied annotations and
  every report that rests on them says so.
- :meth:`ConnectivityWatch.report` is a pure evaluation over the recorded
  history: state transitions, post-expiry unrestricted access, and the
  evidence + findings that follow from them.

Temporal gating lives here, in code; the :mod:`portallens.security.checks`
registry stays evidence-keyed — the watch *emits* qualifying evidence and the
registered ``post_expiry_access`` check turns it into a finding.

An ``unrestricted`` classification means the probe received its expected
unrestricted response (status, and body marker where the profile declares
one) — i.e. internet reachability was verified, not assumed.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from portallens.evidence import Evidence, EvidenceType
from portallens.portal import SecurityFinding
from portallens.security.checks import run_checks
from portallens.wifi.captive_portal import CaptivePortalProbeResult
from portallens.wifi.gateway_status import (
    GatewaySessionInfo,
    matches_payment_code_shape,
)
from portallens.wifi.local_snapshot import (
    LocalNetworkSnapshot,
    snapshot_from_journal,
    snapshot_to_journal,
)


class WatchSampleState(str, Enum):
    """Normalized classification of one watched probe outcome."""

    UNRESTRICTED = "unrestricted"  # verified: expected unrestricted response received
    CAPTIVE = "captive"            # portal intercepted the probe
    UNKNOWN = "unknown"            # probed, but captivity could not be classified
    ERROR = "error"                # the probe itself failed


class PortalClaim(str, Enum):
    """What the portal itself claimed when the user last looked at it.

    Recorded rather than probed: fetching the portal while measuring can be
    the very request that resets the hotspot session, so the observation is
    the user's, and the report says which claim came from where.
    """

    PURCHASE_REQUIRED = "purchase_required"
    LOGIN_REQUIRED = "login_required"
    ACTIVE_SESSION = "active_session"
    UNKNOWN = "unknown"


class WatchBoundaryKind(str, Enum):
    """A user-recorded billing milestone used to interpret samples."""

    PACKAGE_EXPIRY = "package_expiry"
    PACKAGE_RENEWAL = "package_renewal"


@dataclass(frozen=True)
class WatchBoundary:
    """One user-recorded billing milestone with a timezone-aware instant."""

    kind: WatchBoundaryKind
    at: datetime
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, WatchBoundaryKind):
            object.__setattr__(self, "kind", WatchBoundaryKind(str(self.kind)))
        if self.at.tzinfo is None:
            raise ValueError("boundary time must be timezone-aware")


@dataclass(frozen=True)
class WatchSample:
    """One timestamped probe outcome inside a connection epoch.

    ``seconds_remaining`` / ``can_extend_session`` carry RFC 8908 session
    fields when the probed network reported them — corroborating evidence
    about what the *provider* believed the session state was.
    """

    epoch: int
    state: WatchSampleState
    profile_name: str
    observed_at: datetime
    portal_url: str | None = None
    seconds_remaining: int | float | None = None
    can_extend_session: bool | None = None
    evidence: tuple[Evidence, ...] = ()
    portal_claim: PortalClaim | None = None
    note: str | None = None
    snapshot: LocalNetworkSnapshot | None = None
    gateway_session: GatewaySessionInfo | None = None
    gateway_fetch_perturbed: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, WatchSampleState):
            object.__setattr__(self, "state", WatchSampleState(str(self.state)))
        if self.portal_claim is not None and not isinstance(self.portal_claim, PortalClaim):
            object.__setattr__(self, "portal_claim", PortalClaim(str(self.portal_claim)))
        if self.observed_at.tzinfo is None:
            raise ValueError("sample time must be timezone-aware")
        if self.epoch < 0:
            raise ValueError("epoch must be non-negative")


@dataclass(frozen=True)
class WatchTransition:
    """A classification change the watch observed.

    ``from_state`` is ``None`` when the sample is the first the watch has
    seen in its epoch and no earlier epoch contributed a comparison point.
    ``new_epoch`` is ``True`` when the sample opened a fresh connection
    epoch — i.e. the change was observed *after a reconnect*.
    """

    from_state: WatchSampleState | None
    to_state: WatchSampleState
    epoch: int
    observed_at: datetime
    new_epoch: bool = False

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("transition time must be timezone-aware")


_POST_EXPIRY_EVIDENCE_KEY = "watch:post-expiry-access"
_EXPIRED_SESSION_EVIDENCE_KEY = "watch:expired-session-reported"
_TRANSITION_EVIDENCE_KEY = "watch:state-transition"
_PORTAL_MISMATCH_EVIDENCE_KEY = "watch:portal-claim-mismatch"
_GATEWAY_SESSION_KEY = "watch:gateway-session-active"
_GATEWAY_SESSION_NO_PLAN_KEY = "watch:gateway-session-no-plan"
_GATEWAY_SESSION_PAYMENT_CODE_KEY = "watch:gateway-session-username-payment-code-shape"
_GATEWAY_STATUS_FETCH_KEY = "watch:gateway-status-fetch"
_GATEWAY_STATUS_PERTURBATION_KEY = "watch:gateway-status-perturbation"

#: Claims that contradict verified internet access.
_NO_PACKAGE_CLAIMS = frozenset({PortalClaim.PURCHASE_REQUIRED, PortalClaim.LOGIN_REQUIRED})


@dataclass(frozen=True)
class AccessWatchReport:
    """The evaluated result of a :class:`ConnectivityWatch`.

    Carries the recorded history (samples, boundaries), the transitions
    derived from it, watch-emitted evidence (post-expiry access, expired
    sessions reported by the provider, state transitions), and the findings
    the SecurityCheck registry derives from that evidence.
    """

    target: str | None
    samples: tuple[WatchSample, ...]
    boundaries: tuple[WatchBoundary, ...]
    transitions: tuple[WatchTransition, ...]
    evidence: tuple[Evidence, ...]
    findings: tuple[SecurityFinding, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


Clock = Callable[[], datetime]


class ConnectivityWatch:
    """Accumulate probe outcomes, boundaries, and epochs; evaluate on demand.

    The watch holds no network resources — the caller runs probes through
    :class:`~portallens.wifi.captive_portal.CaptivePortalDetector` and feeds
    the results here. All state is in-memory; persistence is a later slice
    (backlog: Wi-Fi live-event persistence).
    """

    def __init__(self, *, target: str | None = None, clock: Clock | None = None) -> None:
        self._target = target
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._samples: list[WatchSample] = []
        self._boundaries: list[WatchBoundary] = []
        self._epoch = 0

    @property
    def epoch(self) -> int:
        """The current connection epoch."""

        return self._epoch

    @property
    def samples(self) -> tuple[WatchSample, ...]:
        return tuple(self._samples)

    @property
    def boundaries(self) -> tuple[WatchBoundary, ...]:
        return tuple(self._boundaries)

    def begin_epoch(self) -> int:
        """Mark a (re)connection episode and return the new epoch id.

        The first epoch is 0 — samples recorded before any ``begin_epoch``
        belong to the connection that was already active when watching
        started. Call this when the host reports a reconnect so the report
        can distinguish "still connected" from "reconnected".
        """

        self._epoch += 1
        return self._epoch

    def add_boundary(
        self,
        kind: WatchBoundaryKind,
        *,
        at: datetime | None = None,
        note: str | None = None,
    ) -> WatchBoundary:
        """Record a user-observed billing milestone (expiry or renewal)."""

        boundary = WatchBoundary(kind=kind, at=at or self._clock(), note=note)
        self._boundaries.append(boundary)
        return boundary

    @property
    def target(self) -> str | None:
        """Label of the watched network, when one was supplied."""

        return self._target

    def record(
        self,
        result: CaptivePortalProbeResult,
        *,
        at: datetime | None = None,
        portal_claim: PortalClaim | None = None,
        note: str | None = None,
        snapshot: LocalNetworkSnapshot | None = None,
        gateway_session: GatewaySessionInfo | None = None,
        gateway_fetch_perturbed: bool | None = None,
    ) -> WatchSample:
        """Fold one bounded probe result into the watched history.

        ``gateway_session`` / ``gateway_fetch_perturbed`` describe an
        authorized gateway status fetch the caller bracketed around this
        probe (see ADR-28); the watch only records what it was told — the
        network behaviour stays the caller's.
        """

        metadata = result.metadata
        sample = WatchSample(
            epoch=self._epoch,
            state=probe_state(result),
            profile_name=result.profile_name,
            observed_at=at or self._clock(),
            portal_url=result.portal_url,
            seconds_remaining=metadata.seconds_remaining if metadata else None,
            can_extend_session=metadata.can_extend_session if metadata else None,
            evidence=result.evidence,
            portal_claim=portal_claim,
            note=note,
            snapshot=snapshot,
            gateway_session=gateway_session,
            gateway_fetch_perturbed=gateway_fetch_perturbed,
        )
        self._samples.append(sample)
        return sample

    def report(self) -> AccessWatchReport:
        """Evaluate the recorded history (pure; does not mutate state)."""

        transitions = _transitions(self._samples)
        evidence = list(_transition_evidence(transitions, self._target))
        evidence.extend(_post_expiry_evidence(self._samples, self._boundaries, self._target))
        evidence.extend(_expired_session_evidence(self._samples, self._target))
        evidence.extend(_portal_claim_mismatch_evidence(self._samples, self._target))
        evidence.extend(_gateway_session_evidence(self._samples, self._target))
        findings = run_checks(evidence)
        notes = [
            "Billing milestones are user-recorded annotations: a read-only "
            "watch cannot observe the billing system, so post-expiry "
            "findings rest on the accuracy of the recorded boundary times.",
            "An 'unrestricted' sample means the probe received its expected "
            "unrestricted response — internet reachability was verified for "
            "that sample, not inferred.",
        ]
        if any(s.gateway_session is not None for s in self._samples):
            notes.append(
                "The gateway session view comes from an authorized fetch of "
                "the hotspot status page, bracketed by connectivity probes; "
                "if the fetch perturbed the session the report says so."
            )
        return AccessWatchReport(
            target=self._target,
            samples=tuple(self._samples),
            boundaries=tuple(self._boundaries),
            transitions=transitions,
            evidence=tuple(evidence),
            findings=tuple(findings),
            notes=tuple(notes),
        )

    # ------------------------------------------------------------------
    # Journal — the on-disk form, so a watch survives between invocations
    # (each real reconnect is a separate run of the tool).
    # ------------------------------------------------------------------

    def to_journal(self) -> dict[str, object]:
        """Return the serializable form of this watch."""

        return {
            "version": JOURNAL_VERSION,
            "target": self._target,
            "epoch": self._epoch,
            "boundaries": [
                {"kind": b.kind.value, "at": b.at.isoformat(), "note": b.note}
                for b in self._boundaries
            ],
            "samples": [
                {
                    "epoch": s.epoch,
                    "state": s.state.value,
                    "profile_name": s.profile_name,
                    "observed_at": s.observed_at.isoformat(),
                    "portal_url": s.portal_url,
                    "seconds_remaining": s.seconds_remaining,
                    "can_extend_session": s.can_extend_session,
                    "portal_claim": s.portal_claim.value if s.portal_claim else None,
                    "note": s.note,
                    "snapshot": snapshot_to_journal(s.snapshot) if s.snapshot else None,
                    "gateway_session": _session_to_journal(s.gateway_session),
                    "gateway_fetch_perturbed": s.gateway_fetch_perturbed,
                }
                for s in self._samples
            ],
        }

    @classmethod
    def from_journal(
        cls,
        payload: object,
        *,
        clock: Clock | None = None,
        target: str | None = None,
    ) -> ConnectivityWatch:
        """Rebuild a watch from :meth:`to_journal` output.

        ``target`` labels a journal that carries none; a journal already
        labelled with a different network is refused rather than silently
        mixing two targets' observations.
        """

        data = _journal_mapping(payload)
        version = data.get("version")
        if version not in _SUPPORTED_JOURNAL_VERSIONS:
            raise ValueError(
                f"unsupported watch journal version {version!r} "
                f"(this build writes version {JOURNAL_VERSION})"
            )
        stored_target = _optional_str(data.get("target"), "target")
        if target is not None and stored_target not in (None, target):
            raise ValueError(
                f"watch journal belongs to target {stored_target!r}, not {target!r}"
            )
        epoch = data.get("epoch", 0)
        if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
            raise ValueError("watch journal epoch must be a non-negative integer")

        watch = cls(target=stored_target or target, clock=clock)
        watch._epoch = epoch
        for entry in _journal_list(data.get("boundaries"), "boundaries"):
            item = _journal_mapping(entry)
            watch._boundaries.append(
                WatchBoundary(
                    kind=WatchBoundaryKind(_required_str(item.get("kind"), "kind")),
                    at=_journal_time(item.get("at"), "boundary"),
                    note=_optional_str(item.get("note"), "note"),
                )
            )
        for entry in _journal_list(data.get("samples"), "samples"):
            item = _journal_mapping(entry)
            sample_epoch = item.get("epoch", 0)
            if not isinstance(sample_epoch, int) or isinstance(sample_epoch, bool):
                raise ValueError("watch journal sample epoch must be an integer")
            watch._samples.append(
                WatchSample(
                    epoch=sample_epoch,
                    state=WatchSampleState(_required_str(item.get("state"), "state")),
                    profile_name=_required_str(item.get("profile_name"), "profile_name"),
                    observed_at=_journal_time(item.get("observed_at"), "sample"),
                    portal_url=_optional_str(item.get("portal_url"), "portal_url"),
                    seconds_remaining=_optional_number(item.get("seconds_remaining")),
                    can_extend_session=_optional_bool_value(item.get("can_extend_session")),
                    portal_claim=_portal_claim_value(item.get("portal_claim")),
                    note=_optional_str(item.get("note"), "note"),
                    snapshot=_journal_snapshot(item.get("snapshot")),
                    gateway_session=_journal_gateway_session(item.get("gateway_session")),
                    gateway_fetch_perturbed=_optional_bool_value(
                        item.get("gateway_fetch_perturbed")
                    ),
                )
            )
        return watch


def probe_state(result: CaptivePortalProbeResult) -> WatchSampleState:
    """Classify one bounded probe outcome (the watch's normalization)."""

    if result.captive is True:
        return WatchSampleState.CAPTIVE
    if result.captive is False:
        return WatchSampleState.UNRESTRICTED
    if result.error is not None:
        return WatchSampleState.ERROR
    return WatchSampleState.UNKNOWN


def _transitions(samples: list[WatchSample]) -> tuple[WatchTransition, ...]:
    transitions: list[WatchTransition] = []
    previous: WatchSample | None = None
    for sample in samples:
        new_epoch = previous is not None and sample.epoch != previous.epoch
        if previous is None or sample.state != previous.state:
            transitions.append(
                WatchTransition(
                    from_state=previous.state if previous else None,
                    to_state=sample.state,
                    epoch=sample.epoch,
                    observed_at=sample.observed_at,
                    new_epoch=new_epoch,
                )
            )
        previous = sample
    return tuple(transitions)


def _transition_evidence(
    transitions: tuple[WatchTransition, ...],
    target: str | None,
) -> tuple[Evidence, ...]:
    evidence: list[Evidence] = []
    for transition in transitions:
        if transition.from_state is None:
            continue
        evidence.append(
            _watch_evidence(
                target,
                _TRANSITION_EVIDENCE_KEY,
                f"{transition.from_state.value}->{transition.to_state.value}",
                (
                    f"Connectivity classification changed across "
                    f"{'a reconnect (new connection epoch)' if transition.new_epoch else 'the same connection'}."
                ),
                observed_at=transition.observed_at,
            )
        )
    return tuple(evidence)


def _post_expiry_evidence(
    samples: list[WatchSample],
    boundaries: list[WatchBoundary],
    target: str | None,
) -> tuple[Evidence, ...]:
    """One evidence record per unrestricted sample not covered by a renewal."""

    expiries = [b for b in boundaries if b.kind is WatchBoundaryKind.PACKAGE_EXPIRY]
    renewals = [b for b in boundaries if b.kind is WatchBoundaryKind.PACKAGE_RENEWAL]
    evidence: list[Evidence] = []
    for sample in samples:
        if sample.state is not WatchSampleState.UNRESTRICTED:
            continue
        prior_expiries = [b for b in expiries if b.at <= sample.observed_at]
        if not prior_expiries:
            continue
        latest_expiry = max(prior_expiries, key=lambda b: b.at)
        covering = [b for b in renewals if latest_expiry.at <= b.at <= sample.observed_at]
        if covering:
            continue
        evidence.append(
            _watch_evidence(
                target,
                _POST_EXPIRY_EVIDENCE_KEY,
                "unrestricted",
                (
                    "Verified unrestricted internet access after the recorded "
                    f"package expiry at {latest_expiry.at.isoformat()}, with no "
                    "recorded renewal before this sample."
                ),
                observed_at=sample.observed_at,
            )
        )
    return tuple(evidence)


def _portal_claim_mismatch_evidence(
    samples: list[WatchSample],
    target: str | None,
) -> tuple[Evidence, ...]:
    """Flag samples where the portal denied a package while access worked.

    This is the signature the tool could not previously see: the gateway
    authorizes traffic and the portal tells the user to buy, in the same
    moment. It is recorded from the user's observation, not from a probe,
    because requesting the portal can itself reset the session.
    """

    evidence: list[Evidence] = []
    for sample in samples:
        if sample.state is not WatchSampleState.UNRESTRICTED:
            continue
        if sample.portal_claim not in _NO_PACKAGE_CLAIMS:
            continue
        claim = sample.portal_claim.value
        evidence.append(
            _watch_evidence(
                target,
                _PORTAL_MISMATCH_EVIDENCE_KEY,
                claim,
                (
                    "Internet access was verified while the portal showed "
                    f"{claim.replace('_', ' ')} - the portal's view of the package "
                    "and the gateway's authorization disagree."
                ),
                observed_at=sample.observed_at,
            )
        )
    return tuple(evidence)


def _expired_session_evidence(
    samples: list[WatchSample],
    target: str | None,
) -> tuple[Evidence, ...]:
    """Corroboration from the provider's own RFC 8908 session fields."""

    evidence: list[Evidence] = []
    for sample in samples:
        if sample.state is not WatchSampleState.UNRESTRICTED:
            continue
        if sample.seconds_remaining is None or sample.seconds_remaining > 0:
            continue
        evidence.append(
            _watch_evidence(
                target,
                _EXPIRED_SESSION_EVIDENCE_KEY,
                str(sample.seconds_remaining),
                (
                    "The network's own RFC 8908 session data reported no time "
                    "remaining while the probe verified unrestricted access — "
                    "the provider believed the session had expired."
                ),
                observed_at=sample.observed_at,
            )
        )
    return tuple(evidence)


def _gateway_session_evidence(
    samples: list[WatchSample],
    target: str | None,
) -> tuple[Evidence, ...]:
    """Evaluate the gateway's own session view, recorded by an authorized fetch.

    The temporal/billing logic stays in code (the registry stays
    evidence-keyed): an active session with an empty plan and every limit
    "Not assigned" is the signature of access with no purchased package
    enforcing it; a username in a payment-transaction-code shape suggests the
    billing integration named the session after a payment. Both are emitted
    as evidence and the checks registry turns them into findings.
    """

    evidence: list[Evidence] = []
    for sample in samples:
        session = sample.gateway_session
        if session is None:
            continue
        if not session.active:
            continue
        evidence.append(
            _watch_evidence(
                target,
                _GATEWAY_SESSION_KEY,
                session.username or "unknown",
                (
                    "The gateway's hotspot status page shows an active session "
                    f"for username {session.username!r} (plan: "
                    f"{session.plan or '(empty)'}; session-left: {session.session_left!r}; "
                    f"expires-on: {session.expires_on!r}; bytes-left: {session.bytes_left!r})."
                ),
                observed_at=sample.observed_at,
            )
        )
        if sample.gateway_fetch_perturbed is True:
            evidence.append(
                _watch_evidence(
                    target,
                    _GATEWAY_STATUS_PERTURBATION_KEY,
                    "classification_changed",
                    (
                        "The connectivity classification changed across the "
                        "gateway status fetch: the fetch may have perturbed "
                        "(reset or re-issued) the hotspot session. Treat the "
                        "session fields above as post-perturbation state."
                    ),
                    observed_at=sample.observed_at,
                )
            )
        else:
            evidence.append(
                _watch_evidence(
                    target,
                    _GATEWAY_STATUS_FETCH_KEY,
                    "no_classification_change",
                    (
                        "The connectivity classification was unchanged across "
                        "the gateway status fetch — this fetch did not visibly "
                        "perturb the hotspot session."
                    ),
                    observed_at=sample.observed_at,
                )
            )
        if session.plan is None and session.limits_unassigned:
            evidence.append(
                _watch_evidence(
                    target,
                    _GATEWAY_SESSION_NO_PLAN_KEY,
                    session.username or "unknown",
                    (
                        "The gateway holds an active hotspot session with no "
                        "plan attached and every limit 'Not assigned' — traffic "
                        "is authorized with no time or byte cap from a purchased "
                        "package."
                    ),
                    observed_at=sample.observed_at,
                )
            )
        if matches_payment_code_shape(session.username):
            evidence.append(
                _watch_evidence(
                    target,
                    _GATEWAY_SESSION_PAYMENT_CODE_KEY,
                    session.username or "",
                    (
                        "The session username has a payment-transaction-code "
                        "shape (10 uppercase alphanumerics, e.g. a mobile-money "
                        "receipt code) — a format inference suggesting the "
                        "billing integration named the session after a payment."
                    ),
                    observed_at=sample.observed_at,
                )
            )
    return tuple(evidence)


def _watch_evidence(
    target: str | None,
    key: str,
    value: str,
    note: str,
    *,
    observed_at: datetime,
) -> Evidence:
    label = target or "session"
    return Evidence(
        type=EvidenceType.CAPTIVE_PORTAL_STATUS,
        source=f"wifi-watch://{label}",
        key=key,
        value=value,
        note=f"{note} Observed at {observed_at.isoformat()}.",
    )


JOURNAL_VERSION = 2
#: Journals written by earlier builds (probe/claim/note only) remain readable.
_SUPPORTED_JOURNAL_VERSIONS = (1, 2)


def default_watch_journal_path() -> str:
    """Where the watch journal lives when no path is given.

    Precedence: ``$PORTALLENS_WATCH`` -> ``$XDG_DATA_HOME/portallens/watch.json``
    -> ``~/.local/share/portallens/watch.json``, alongside the investigations
    database.
    """

    explicit = os.environ.get("PORTALLENS_WATCH")
    if explicit:
        return explicit
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return str(base / "portallens" / "watch.json")


def load_watch_journal(
    path: str | os.PathLike[str],
    *,
    clock: Clock | None = None,
    target: str | None = None,
) -> ConnectivityWatch:
    """Load a watch journal, or start an empty watch when the file is absent."""

    journal = Path(path)
    if not journal.exists():
        return ConnectivityWatch(target=target, clock=clock)
    return ConnectivityWatch.from_journal(
        json.loads(journal.read_text(encoding="utf-8")),
        clock=clock,
        target=target,
    )


def save_watch_journal(path: str | os.PathLike[str], watch: ConnectivityWatch) -> None:
    """Write the journal atomically so an interrupted run cannot corrupt it."""

    journal = Path(path)
    journal.parent.mkdir(parents=True, exist_ok=True)
    staging = journal.with_name(journal.name + ".tmp")
    staging.write_text(json.dumps(watch.to_journal(), indent=2) + "\n", encoding="utf-8")
    os.replace(staging, journal)


def _journal_snapshot(value: object) -> LocalNetworkSnapshot | None:
    if value is None:
        return None
    return snapshot_from_journal(value)


def _session_to_journal(session: GatewaySessionInfo | None) -> dict[str, object] | None:
    if session is None:
        return None
    return {
        "username": session.username,
        "mac": session.mac,
        "ip": session.ip,
        "plan": session.plan,
        "start_time": session.start_time,
        "session_left": session.session_left,
        "expires_on": session.expires_on,
        "bytes_left": session.bytes_left,
        "source_url": session.source_url,
    }


def _journal_gateway_session(value: object) -> GatewaySessionInfo | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("watch journal gateway_session must be an object or null")
    return GatewaySessionInfo(
        username=_optional_str(value.get("username"), "gateway_session.username"),
        mac=_optional_str(value.get("mac"), "gateway_session.mac"),
        ip=_optional_str(value.get("ip"), "gateway_session.ip"),
        plan=_optional_str(value.get("plan"), "gateway_session.plan"),
        start_time=_optional_str(value.get("start_time"), "gateway_session.start_time"),
        session_left=_optional_str(value.get("session_left"), "gateway_session.session_left"),
        expires_on=_optional_str(value.get("expires_on"), "gateway_session.expires_on"),
        bytes_left=_optional_str(value.get("bytes_left"), "gateway_session.bytes_left"),
        source_url=_optional_str(value.get("source_url"), "gateway_session.source_url") or "",
    )


def _journal_mapping(value: object) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise ValueError("watch journal must be a JSON object")
    return value


def _journal_list(value: object, field_name: str) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"watch journal {field_name} must be a list")
    return list(value)


def _required_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"watch journal {field_name} must be a non-empty string")
    return value


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"watch journal {field_name} must be a string or null")
    return value


def _optional_number(value: object) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("watch journal seconds_remaining must be a number or null")
    return value


def _portal_claim_value(value: object) -> PortalClaim | None:
    if value is None:
        return None
    text = _required_str(value, "portal_claim")
    try:
        return PortalClaim(text)
    except ValueError as exc:
        raise ValueError(f"watch journal portal_claim is not a known claim: {text!r}") from exc


def _optional_bool_value(value: object) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("watch journal can_extend_session must be a boolean or null")
    return value


def _journal_time(value: object, owner: str) -> datetime:
    text = _required_str(value, f"{owner} time")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"watch journal {owner} time is not ISO 8601: {text!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"watch journal {owner} time must be timezone-aware")
    return parsed


__all__ = [
    "JOURNAL_VERSION",
    "AccessWatchReport",
    "ConnectivityWatch",
    "PortalClaim",
    "WatchBoundary",
    "WatchBoundaryKind",
    "WatchSample",
    "WatchSampleState",
    "WatchTransition",
    "default_watch_journal_path",
    "load_watch_journal",
    "probe_state",
    "save_watch_journal",
]
