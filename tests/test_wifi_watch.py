"""Tests for the credential-free connectivity watch (post-expiry access)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from portallens.evidence import EvidenceType, reset_evidence_ids
from portallens.wifi.captive_portal import CaptivePortalMetadata, CaptivePortalProbeResult
from portallens.wifi.watch import (
    AccessWatchReport,
    ConnectivityWatch,
    WatchBoundary,
    WatchBoundaryKind,
    WatchSample,
    WatchSampleState,
    WatchTransition,
)

T0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


def _result(
    captive: bool | None,
    *,
    error: str | None = None,
    metadata: CaptivePortalMetadata | None = None,
    profile: str = "windows-ncsi",
) -> CaptivePortalProbeResult:
    return CaptivePortalProbeResult(
        profile_name=profile,
        probe_url="http://www.msftncsi.com/ncsi.txt",
        captive=captive,
        status_code=200 if error is None else None,
        error=error,
        metadata=metadata,
    )


def _clock(*times: datetime):
    queue = iter(times)
    return lambda: next(queue)


class TestSampleStateMapping:
    def test_captive_result_maps_to_captive(self) -> None:
        watch = ConnectivityWatch()
        sample = watch.record(_result(True), at=T0)
        assert sample.state is WatchSampleState.CAPTIVE

    def test_unrestricted_result_maps_to_unrestricted(self) -> None:
        watch = ConnectivityWatch()
        sample = watch.record(_result(False), at=T0)
        assert sample.state is WatchSampleState.UNRESTRICTED

    def test_failed_probe_maps_to_error(self) -> None:
        watch = ConnectivityWatch()
        sample = watch.record(_result(None, error="ConnectTimeout"), at=T0)
        assert sample.state is WatchSampleState.ERROR

    def test_unclassified_probe_maps_to_unknown(self) -> None:
        watch = ConnectivityWatch()
        sample = watch.record(_result(None), at=T0)
        assert sample.state is WatchSampleState.UNKNOWN


class TestWatchAccumulation:
    def test_record_uses_clock_and_initial_epoch(self) -> None:
        watch = ConnectivityWatch(clock=_clock(T0))
        sample = watch.record(_result(False))
        assert sample.observed_at == T0
        assert sample.epoch == 0

    def test_begin_epoch_starts_a_new_episode(self) -> None:
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0)
        epoch = watch.begin_epoch()
        sample = watch.record(_result(False), at=T0 + timedelta(minutes=1))
        assert epoch == 1
        assert sample.epoch == 1

    def test_naive_sample_time_rejected(self) -> None:
        watch = ConnectivityWatch()
        with pytest.raises(ValueError, match="timezone-aware"):
            watch.record(_result(False), at=T0.replace(tzinfo=None))

    def test_naive_boundary_time_rejected(self) -> None:
        watch = ConnectivityWatch()
        with pytest.raises(ValueError, match="timezone-aware"):
            watch.add_boundary(
                WatchBoundaryKind.PACKAGE_EXPIRY,
                at=T0.replace(tzinfo=None),
            )

    def test_boundary_uses_clock_by_default(self) -> None:
        watch = ConnectivityWatch(clock=_clock(T0))
        boundary = watch.add_boundary(WatchBoundaryKind.PACKAGE_EXPIRY)
        assert boundary.at == T0
        assert boundary.kind is WatchBoundaryKind.PACKAGE_EXPIRY


class TestTransitions:
    def test_first_sample_opens_the_history(self) -> None:
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0)
        (transition,) = watch.report().transitions
        assert transition.from_state is None
        assert transition.to_state is WatchSampleState.UNRESTRICTED
        assert transition.new_epoch is False

    def test_same_state_produces_no_change_transition(self) -> None:
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0)
        watch.record(_result(False), at=T0 + timedelta(minutes=1))
        changes = [t for t in watch.report().transitions if t.from_state is not None]
        assert changes == []

    def test_in_epoch_flip_is_a_transition(self) -> None:
        watch = ConnectivityWatch()
        watch.record(_result(True), at=T0)
        watch.record(_result(False), at=T0 + timedelta(minutes=1))
        (transition,) = [t for t in watch.report().transitions if t.from_state is not None]
        assert transition.from_state is WatchSampleState.CAPTIVE
        assert transition.to_state is WatchSampleState.UNRESTRICTED
        assert transition.new_epoch is False

    def test_flip_after_reconnect_is_flagged_as_new_epoch(self) -> None:
        watch = ConnectivityWatch()
        watch.record(_result(True), at=T0)
        watch.begin_epoch()
        watch.record(_result(False), at=T0 + timedelta(minutes=5))
        (transition,) = [t for t in watch.report().transitions if t.from_state is not None]
        assert transition.from_state is WatchSampleState.CAPTIVE
        assert transition.to_state is WatchSampleState.UNRESTRICTED
        assert transition.new_epoch is True


class TestPostExpiryAccess:
    def _expired_watch(self) -> ConnectivityWatch:
        """The reported scenario: expiry, reconnect, access back with no payment."""
        watch = ConnectivityWatch(target="maz.wifi")
        watch.record(_result(False), at=T0)
        watch.add_boundary(WatchBoundaryKind.PACKAGE_EXPIRY, at=T0 + timedelta(hours=1))
        watch.begin_epoch()
        watch.record(_result(False), at=T0 + timedelta(hours=1, minutes=10))
        return watch

    def test_unrestricted_before_expiry_is_not_flagged(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0)
        report = watch.report()
        assert not any(e.key == "watch:post-expiry-access" for e in report.evidence)
        assert report.findings == ()

    def test_unrestricted_after_expiry_is_flagged(self) -> None:
        reset_evidence_ids()
        report = self._expired_watch().report()
        matches = [e for e in report.evidence if e.key == "watch:post-expiry-access"]
        assert len(matches) == 1
        assert matches[0].type is EvidenceType.CAPTIVE_PORTAL_STATUS
        assert matches[0].value == "unrestricted"
        assert "maz.wifi" in matches[0].source

    def test_post_expiry_access_raises_a_finding(self) -> None:
        reset_evidence_ids()
        report = self._expired_watch().report()
        (finding,) = report.findings
        assert finding.check_slug == "post_expiry_access"
        assert finding.severity.value == "medium"
        assert finding.confidence == 80
        assert "provisional" in (finding.verification_status or "")

    def test_renewal_between_expiry_and_sample_covers_access(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.add_boundary(WatchBoundaryKind.PACKAGE_EXPIRY, at=T0)
        watch.add_boundary(WatchBoundaryKind.PACKAGE_RENEWAL, at=T0 + timedelta(minutes=5))
        watch.record(_result(False), at=T0 + timedelta(minutes=10))
        report = watch.report()
        assert not any(e.key == "watch:post-expiry-access" for e in report.evidence)
        assert report.findings == ()

    def test_renewal_before_expiry_does_not_cover(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.add_boundary(WatchBoundaryKind.PACKAGE_RENEWAL, at=T0)
        watch.add_boundary(WatchBoundaryKind.PACKAGE_EXPIRY, at=T0 + timedelta(hours=1))
        watch.record(_result(False), at=T0 + timedelta(hours=1, minutes=1))
        report = watch.report()
        assert any(e.key == "watch:post-expiry-access" for e in report.evidence)

    def test_captive_sample_after_expiry_is_not_flagged(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.add_boundary(WatchBoundaryKind.PACKAGE_EXPIRY, at=T0)
        watch.record(_result(True), at=T0 + timedelta(minutes=1))
        report = watch.report()
        assert not any(e.key == "watch:post-expiry-access" for e in report.evidence)
        assert report.findings == ()

    def test_error_sample_after_expiry_is_not_flagged(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.add_boundary(WatchBoundaryKind.PACKAGE_EXPIRY, at=T0)
        watch.record(_result(None, error="ConnectTimeout"), at=T0 + timedelta(minutes=1))
        report = watch.report()
        assert not any(e.key == "watch:post-expiry-access" for e in report.evidence)


class TestExpiredSessionCorroboration:
    def test_seconds_remaining_zero_while_unrestricted_is_evidence(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        metadata = CaptivePortalMetadata(captive=False, seconds_remaining=0)
        watch.record(_result(False, metadata=metadata), at=T0)
        report = watch.report()
        matches = [e for e in report.evidence if e.key == "watch:expired-session-reported"]
        assert len(matches) == 1
        assert matches[0].value == "0"

    def test_positive_seconds_remaining_is_not_evidence(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        metadata = CaptivePortalMetadata(captive=False, seconds_remaining=300)
        watch.record(_result(False, metadata=metadata), at=T0)
        report = watch.report()
        assert not any(e.key == "watch:expired-session-reported" for e in report.evidence)


class TestReportShape:
    def test_report_is_deterministic_about_history(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0)
        first = watch.report()
        second = watch.report()
        assert first.samples == second.samples
        assert first.boundaries == second.boundaries
        assert first.transitions == second.transitions

    def test_report_carries_honesty_notes(self) -> None:
        watch = ConnectivityWatch()
        report = watch.report()
        assert any("user-recorded" in note for note in report.notes)

    def test_transition_evidence_mentions_reconnects(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch(target="maz.wifi")
        watch.record(_result(True), at=T0)
        watch.begin_epoch()
        watch.record(_result(False), at=T0 + timedelta(minutes=5))
        report = watch.report()
        transitions = [e for e in report.evidence if e.key == "watch:state-transition"]
        assert len(transitions) == 1
        assert transitions[0].value == "captive->unrestricted"
        assert "reconnect" in (transitions[0].note or "")

    def test_models_are_frozen(self) -> None:
        sample = WatchSample(
            epoch=0,
            state=WatchSampleState.UNRESTRICTED,
            profile_name="windows-ncsi",
            observed_at=T0,
        )
        with pytest.raises(AttributeError):
            sample.epoch = 1  # type: ignore[misc]
        boundary = WatchBoundary(kind=WatchBoundaryKind.PACKAGE_EXPIRY, at=T0)
        with pytest.raises(AttributeError):
            boundary.kind = WatchBoundaryKind.PACKAGE_RENEWAL  # type: ignore[misc]
        transition = WatchTransition(
            from_state=None,
            to_state=WatchSampleState.UNRESTRICTED,
            epoch=0,
            observed_at=T0,
        )
        with pytest.raises(AttributeError):
            transition.new_epoch = True  # type: ignore[misc]

    def test_report_type_exports(self) -> None:
        assert AccessWatchReport is not None
