"""Tests for the credential-free connectivity watch (post-expiry access)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from portallens.evidence import EvidenceType, reset_evidence_ids
from portallens.wifi.captive_portal import CaptivePortalMetadata, CaptivePortalProbeResult
from portallens.wifi.gateway_status import GatewaySessionInfo
from portallens.wifi.local_snapshot import LocalNetworkSnapshot
from portallens.wifi.watch import (
    JOURNAL_VERSION,
    AccessWatchReport,
    ConnectivityWatch,
    PortalClaim,
    WatchBoundary,
    WatchBoundaryKind,
    WatchSample,
    WatchSampleState,
    WatchTransition,
    probe_state,
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


class TestPortalClaim:
    def test_claim_is_recorded_on_the_sample(self) -> None:
        watch = ConnectivityWatch()
        sample = watch.record(_result(False), at=T0, portal_claim=PortalClaim.PURCHASE_REQUIRED)
        assert sample.portal_claim is PortalClaim.PURCHASE_REQUIRED

    def test_claim_accepts_its_string_value(self) -> None:
        watch = ConnectivityWatch()
        sample = watch.record(_result(False), at=T0, portal_claim="login_required")  # type: ignore[arg-type]
        assert sample.portal_claim is PortalClaim.LOGIN_REQUIRED

    def test_online_while_portal_asks_to_purchase_is_the_mismatch(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch(target="maz.wifi")
        watch.record(
            _result(False),
            at=T0,
            portal_claim=PortalClaim.PURCHASE_REQUIRED,
            note="tethered laptop opened the portal",
        )
        report = watch.report()
        matches = [e for e in report.evidence if e.key == "watch:portal-claim-mismatch"]
        assert len(matches) == 1
        assert matches[0].value == "purchase_required"
        (finding,) = report.findings
        assert finding.check_slug == "portal_claim_mismatch"
        assert finding.severity.value == "medium"
        assert finding.confidence == 78

    def test_login_page_while_online_is_also_a_mismatch(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0, portal_claim=PortalClaim.LOGIN_REQUIRED)
        report = watch.report()
        assert any(e.key == "watch:portal-claim-mismatch" for e in report.evidence)

    def test_active_session_claim_is_consistent(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0, portal_claim=PortalClaim.ACTIVE_SESSION)
        report = watch.report()
        assert not any(e.key == "watch:portal-claim-mismatch" for e in report.evidence)
        assert report.findings == ()

    def test_claim_on_a_captive_sample_is_consistent(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.record(_result(True), at=T0, portal_claim=PortalClaim.PURCHASE_REQUIRED)
        report = watch.report()
        assert not any(e.key == "watch:portal-claim-mismatch" for e in report.evidence)

    def test_mismatch_needs_no_expiry_boundary(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0, portal_claim=PortalClaim.PURCHASE_REQUIRED)
        report = watch.report()
        assert [f.check_slug for f in report.findings] == ["portal_claim_mismatch"]

    def test_journal_roundtrips_claim_and_note(self) -> None:
        watch = ConnectivityWatch(target="maz.wifi")
        watch.record(
            _result(False),
            at=T0,
            portal_claim=PortalClaim.PURCHASE_REQUIRED,
            note="after the other device opened the portal",
        )
        rebuilt = ConnectivityWatch.from_journal(watch.to_journal())
        sample = rebuilt.samples[0]
        assert sample.portal_claim is PortalClaim.PURCHASE_REQUIRED
        assert sample.note == "after the other device opened the portal"

    def test_old_journal_without_claims_still_loads(self) -> None:
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0)
        payload = watch.to_journal()
        for sample in payload["samples"]:  # type: ignore[union-attr]
            sample.pop("portal_claim", None)
            sample.pop("note", None)
        rebuilt = ConnectivityWatch.from_journal(payload)
        assert rebuilt.samples[0].portal_claim is None


def _session(**overrides: object) -> GatewaySessionInfo:
    values: dict[str, object] = {
        "username": "UIBMX5SUY3",
        "mac": "98:AF:65:7C:6A:69",
        "ip": "11.220.2.109",
        "plan": None,
        "start_time": None,
        "session_left": "Not assigned *",
        "expires_on": "Not assigned *",
        "bytes_left": "Not assigned *",
        "source_url": "http://11.220.0.1/status",
    }
    values.update(overrides)
    return GatewaySessionInfo(**values)  # type: ignore[arg-type]


def _snapshot() -> LocalNetworkSnapshot:
    return LocalNetworkSnapshot(
        ssid="KITENGELA@10",
        interface="Wi-Fi",
        client_ipv4="11.220.2.109",
        gateway_ipv4="11.220.0.1",
        gateway_mac="DC:2C:6E:00:06:8C",
        gateway_vendor="MikroTik",
        observed_at=T0,
    )


class TestJournalVersions:
    def test_current_journal_is_version_two(self) -> None:
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0)
        assert watch.to_journal()["version"] == JOURNAL_VERSION == 2

    def test_version_one_journal_still_loads(self) -> None:
        legacy = {
            "version": 1,
            "target": "maz.wifi",
            "epoch": 0,
            "boundaries": [],
            "samples": [
                {
                    "epoch": 0,
                    "state": "unrestricted",
                    "profile_name": "windows-ncsi",
                    "observed_at": T0.isoformat(),
                }
            ],
        }
        rebuilt = ConnectivityWatch.from_journal(legacy)
        assert rebuilt.samples[0].state is WatchSampleState.UNRESTRICTED
        assert rebuilt.samples[0].snapshot is None
        assert rebuilt.samples[0].gateway_session is None

    def test_unknown_version_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unsupported watch journal version"):
            ConnectivityWatch.from_journal({"version": 99})


class TestLocalSnapshotOnSamples:
    def test_snapshot_roundtrips_through_the_journal(self) -> None:
        watch = ConnectivityWatch(target="KITENGELA@10")
        watch.record(_result(False), at=T0, snapshot=_snapshot())
        rebuilt = ConnectivityWatch.from_journal(watch.to_journal())
        assert rebuilt.samples[0].snapshot == _snapshot()

    def test_sample_without_snapshot_stays_none(self) -> None:
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0)
        assert watch.to_journal()["samples"][0]["snapshot"] is None  # type: ignore[index]


class TestGatewaySessionEvidence:
    def test_no_plan_session_raises_both_findings(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch(target="KITENGELA@10")
        watch.record(
            _result(False),
            at=T0,
            snapshot=_snapshot(),
            gateway_session=_session(),
            gateway_fetch_perturbed=False,
        )
        report = watch.report()
        keys = {e.key for e in report.evidence}
        assert "watch:gateway-session-active" in keys
        assert "watch:gateway-session-no-plan" in keys
        assert "watch:gateway-session-username-payment-code-shape" in keys
        assert "watch:gateway-status-fetch" in keys
        slugs = {f.check_slug for f in report.findings}
        assert slugs == {"gateway_session_without_plan", "session_username_payment_code_shape"}

    def test_unperturbed_fetch_records_verification_evidence(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0, gateway_session=_session(), gateway_fetch_perturbed=False)
        report = watch.report()
        (fetch,) = [e for e in report.evidence if e.key == "watch:gateway-status-fetch"]
        assert fetch.value == "no_classification_change"

    def test_perturbed_fetch_records_perturbation_evidence(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0, gateway_session=_session(), gateway_fetch_perturbed=True)
        report = watch.report()
        assert not any(e.key == "watch:gateway-status-fetch" for e in report.evidence)
        (perturb,) = [e for e in report.evidence if e.key == "watch:gateway-status-perturbation"]
        assert "perturbed" in (perturb.note or "")

    def test_profiled_session_has_no_no_plan_evidence(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.record(
            _result(False),
            at=T0,
            gateway_session=_session(
                plan="1 Day", session_left="23h59m", expires_on="2026-10-22", bytes_left="4 GB"
            ),
        )
        report = watch.report()
        keys = {e.key for e in report.evidence}
        assert "watch:gateway-session-active" in keys
        assert "watch:gateway-session-no-plan" not in keys
        assert "watch:gateway-session-username-payment-code-shape" in keys
        assert [f.check_slug for f in report.findings] == ["session_username_payment_code_shape"]

    def test_non_payment_username_has_no_format_finding(self) -> None:
        reset_evidence_ids()
        watch = ConnectivityWatch()
        watch.record(
            _result(False),
            at=T0,
            gateway_session=_session(username="wifikwame", plan="1 Day",
                                     session_left="23h59m", expires_on="2026-10-22", bytes_left="4 GB"),
        )
        report = watch.report()
        assert report.findings == ()

    def test_session_and_perturbation_roundtrip_through_the_journal(self) -> None:
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0, gateway_session=_session(), gateway_fetch_perturbed=True)
        rebuilt = ConnectivityWatch.from_journal(watch.to_journal())
        sample = rebuilt.samples[0]
        assert sample.gateway_session == _session()
        assert sample.gateway_fetch_perturbed is True

    def test_report_mentions_the_fetch_in_notes(self) -> None:
        watch = ConnectivityWatch()
        watch.record(_result(False), at=T0, gateway_session=_session())
        assert any("bracketed" in note for note in watch.report().notes)

    def test_probe_state_export_matches_record_classification(self) -> None:
        watch = ConnectivityWatch()
        sample = watch.record(_result(False), at=T0)
        assert probe_state(_result(False)) is sample.state
