"""CLI-level tests for ``portallens watch``.

These drive the real Click command through CliRunner with the detector's
request function replaced, so no test reaches the network. They cover the
wiring the library tests do not: authorization refusal, journal
accumulation across "reconnects", boundary handling, and output formats.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from click.testing import CliRunner

from portallens.cli import main
from portallens.wifi.captive_portal import (
    CancellationToken,
    CaptivePortalDetector,
    CaptivePortalResponse,
)
from portallens.wifi.gateway_status import GatewaySessionInfo
from portallens.wifi.local_snapshot import LocalNetworkSnapshot

UNRESTRICTED_BODY = "Microsoft NCSI"
PORTAL_URL = "http://maz.wifi/login?dst=http%3A%2F%2Fwww.msftconnecttest.com%2Fredirect"


@pytest.fixture(autouse=True)
def _no_real_host_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every watch test hermetic: no real netsh/ipconfig/arp on the host."""

    monkeypatch.setattr("portallens.cli._watch_snapshot", lambda: None)


def _fixture_snapshot() -> LocalNetworkSnapshot:
    return LocalNetworkSnapshot(
        ssid="KITENGELA@10",
        interface="Wi-Fi",
        client_ipv4="11.220.2.109",
        gateway_ipv4="11.220.0.1",
        gateway_mac="DC:2C:6E:00:06:8C",
        gateway_vendor="MikroTik",
    )


def _fixture_session() -> GatewaySessionInfo:
    return GatewaySessionInfo(
        username="UIBMX5SUY3",
        mac="98:AF:65:7C:6A:69",
        ip="11.220.2.109",
        plan=None,
        start_time=None,
        session_left="Not assigned *",
        expires_on="Not assigned *",
        bytes_left="Not assigned *",
        source_url="http://11.220.0.1/status",
    )


def _detector(*responses: CaptivePortalResponse) -> CaptivePortalDetector:
    queue = list(responses)

    def request(
        url: str,
        headers: Mapping[str, str],
        cancel: CancellationToken,
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> CaptivePortalResponse:
        return queue.pop(0)

    return CaptivePortalDetector(request=request)


def _unrestricted() -> CaptivePortalResponse:
    return CaptivePortalResponse(
        status_code=200,
        headers={"Content-Type": "text/plain"},
        body=UNRESTRICTED_BODY,
    )


def _captive() -> CaptivePortalResponse:
    return CaptivePortalResponse(status_code=302, headers={"Location": PORTAL_URL}, body="")


@pytest.fixture()
def journal(tmp_path: Path) -> Path:
    return tmp_path / "watch.json"


def _watch(
    runner: CliRunner,
    journal: Path,
    *args: str,
) -> object:
    return runner.invoke(
        main,
        ["watch", "--journal", str(journal), *args],
    )


def _patch_detector(monkeypatch: pytest.MonkeyPatch, detector: CaptivePortalDetector) -> None:
    monkeypatch.setattr("portallens.cli._watch_detector", lambda: detector)


class TestAuthorizationGate:
    def test_refuses_without_authorized(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(CliRunner(), journal, "--expiry", "2026-10-20T12:00")
        assert result.exit_code == 2
        assert "--authorized" in result.output
        assert not journal.exists()


class TestFirstObservation:
    def test_unrestricted_after_expiry_raises_finding(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(
            CliRunner(), journal, "--target", "maz.wifi", "--expiry", "2026-10-20T12:00", "--authorized"
        )
        assert result.exit_code == 0, result.output
        assert "post_expiry_access" in result.output
        assert "Internet access available after recorded package expiry" in result.output
        assert journal.exists()

    def test_no_expiry_means_no_finding(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(CliRunner(), journal, "--authorized")
        assert result.exit_code == 0, result.output
        assert "post_expiry_access" not in result.output
        assert "Findings raised: none" in result.output

    def test_captive_sample_is_not_flagged(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_captive()))
        result = _watch(CliRunner(), journal, "--expiry", "2026-10-20T12:00", "--authorized")
        assert result.exit_code == 0, result.output
        assert "post_expiry_access" not in result.output
        assert "captive" in result.output


class TestJournalAcrossReconnects:
    def test_journal_accumulates_and_marks_new_epoch(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runner = CliRunner()
        _patch_detector(monkeypatch, _detector(_captive()))
        first = _watch(runner, journal, "--target", "maz.wifi", "--expiry", "2026-10-20T12:00", "--authorized")
        assert first.exit_code == 0, first.output

        _patch_detector(monkeypatch, _detector(_unrestricted()))
        second = _watch(runner, journal, "--reconnect", "--authorized")
        assert second.exit_code == 0, second.output
        assert "after a reconnect" in second.output

        stored = json.loads(journal.read_text(encoding="utf-8"))
        assert stored["target"] == "maz.wifi"
        assert len(stored["samples"]) == 2
        assert stored["samples"][0]["epoch"] == 0
        assert stored["samples"][1]["epoch"] == 1
        assert stored["samples"][1]["state"] == "unrestricted"

    def test_second_expiry_is_recorded_once_per_run(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runner = CliRunner()
        _patch_detector(monkeypatch, _detector(_captive()))
        _watch(runner, journal, "--expiry", "2026-10-20T12:00", "--authorized")
        _watch(runner, journal, "--reconnect", "--authorized")

        stored = json.loads(journal.read_text(encoding="utf-8"))
        assert len(stored["boundaries"]) == 1


class TestRenewalAndTargets:
    def test_renewal_after_expiry_covers_access(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(
            CliRunner(),
            journal,
            "--expiry",
            "2026-10-20T12:00",
            "--renewal",
            "2026-10-20T12:30",
            "--authorized",
        )
        assert result.exit_code == 0, result.output
        assert "post_expiry_access" not in result.output

    def test_journal_target_mismatch_is_refused(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runner = CliRunner()
        _patch_detector(monkeypatch, _detector(_captive()))
        _watch(runner, journal, "--target", "maz.wifi", "--authorized")

        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(runner, journal, "--target", "other.net", "--authorized")
        assert result.exit_code == 2
        assert "belongs to target" in result.output


class TestBadInput:
    def test_unknown_profile_lists_available(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(CliRunner(), journal, "--profile", "nope", "--authorized")
        assert result.exit_code == 2
        assert "windows-ncsi" in result.output

    def test_invalid_boundary_time_is_rejected(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(CliRunner(), journal, "--expiry", "yesterday", "--authorized")
        assert result.exit_code == 2

    def test_corrupt_journal_is_reported(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        journal.write_text("{not json", encoding="utf-8")
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(CliRunner(), journal, "--authorized")
        # JSONDecodeError derives from ValueError, so the CLI reports it cleanly.
        assert result.exit_code == 2
        assert "Error:" in result.output
        assert "Traceback" not in result.output


class TestJsonFormat:
    def test_json_carries_findings_and_samples(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(
            CliRunner(), journal, "--expiry", "2026-10-20T12:00", "--format", "json", "--authorized"
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["target"] is None
        assert payload["samples"][0]["state"] == "unrestricted"
        assert payload["findings"][0]["check_slug"] == "post_expiry_access"
        assert payload["evidence"][0]["key"].startswith("watch:")


class TestPortalClaim:
    def test_unknown_claim_is_rejected(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(
            CliRunner(),
            journal,
            "--target",
            "maz.wifi",
            "--portal",
            "buy-something",
            "--authorized",
        )
        assert result.exit_code == 2
        assert "is not one of" in result.output
        assert "purchase_required" in result.output

    def test_claim_is_recorded_and_reported(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(
            CliRunner(),
            journal,
            "--target",
            "maz.wifi",
            "--portal",
            "purchase_required",
            "--note",
            "tethered laptop opened the portal",
            "--authorized",
        )
        assert result.exit_code == 0, result.output
        assert "portal_claim_mismatch" in result.output
        assert "tethered laptop opened the portal" in result.output

        stored = json.loads(journal.read_text(encoding="utf-8"))
        assert stored["samples"][0]["portal_claim"] == "purchase_required"
        assert stored["samples"][0]["note"] == "tethered laptop opened the portal"

    def test_active_session_claim_is_consistent(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(CliRunner(), journal, "--portal", "active_session", "--authorized")
        assert result.exit_code == 0, result.output
        assert "portal_claim_mismatch" not in result.output
        assert "Findings raised: none" in result.output


class TestGatewayStatus:
    def _patch_context(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *responses: CaptivePortalResponse,
        session: GatewaySessionInfo | None = None,
        fetch_error: Exception | None = None,
        snapshot: LocalNetworkSnapshot | None = None,
    ) -> None:
        _patch_detector(monkeypatch, _detector(*responses))
        monkeypatch.setattr("portallens.cli._watch_snapshot", lambda: snapshot)

        def fake_fetch(url: str, policy: object) -> GatewaySessionInfo:
            assert url == "http://11.220.0.1/status"
            if fetch_error is not None:
                raise fetch_error
            assert session is not None
            return session

        monkeypatch.setattr("portallens.cli._gateway_status_fetch", fake_fetch)

    def test_guarded_fetch_records_session_and_findings(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_context(
            monkeypatch,
            _unrestricted(),
            _unrestricted(),
            session=_fixture_session(),
            snapshot=_fixture_snapshot(),
        )
        result = _watch(CliRunner(), journal, "--target", "KITENGELA@10", "--gateway-status", "--authorized")
        assert result.exit_code == 0, result.output
        assert "gateway_session_without_plan" in result.output
        assert "session_username_payment_code_shape" in result.output
        assert "Local network" in result.output
        assert "Gateway session view" in result.output

        stored = json.loads(journal.read_text(encoding="utf-8"))
        sample = stored["samples"][0]
        assert sample["snapshot"]["ssid"] == "KITENGELA@10"
        assert sample["gateway_session"]["username"] == "UIBMX5SUY3"
        assert sample["gateway_fetch_perturbed"] is False

    def test_classification_change_is_recorded_as_perturbation(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_context(
            monkeypatch,
            _unrestricted(),
            _captive(),
            session=_fixture_session(),
            snapshot=_fixture_snapshot(),
        )
        result = _watch(CliRunner(), journal, "--gateway-status", "--authorized")
        assert result.exit_code == 0, result.output
        assert "watch:gateway-status-perturbation" in result.output

        stored = json.loads(journal.read_text(encoding="utf-8"))
        assert stored["samples"][0]["gateway_fetch_perturbed"] is True

    def test_missing_gateway_is_reported(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_detector(monkeypatch, _detector(_unrestricted()))
        result = _watch(CliRunner(), journal, "--gateway-status", "--authorized")
        assert result.exit_code == 2
        assert "default gateway" in result.output
        assert not journal.exists()

    def test_gateway_status_refuses_without_authorized(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_context(monkeypatch, _unrestricted(), snapshot=_fixture_snapshot())
        result = _watch(CliRunner(), journal, "--gateway-status")
        assert result.exit_code == 2
        assert "--authorized" in result.output
        assert not journal.exists()

    def test_fetch_failure_is_reported_and_nothing_is_recorded(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_context(
            monkeypatch,
            _unrestricted(),
            fetch_error=ConnectionError("gateway did not answer"),
            snapshot=_fixture_snapshot(),
        )
        result = _watch(CliRunner(), journal, "--gateway-status", "--authorized")
        assert result.exit_code == 2
        assert "gateway status fetch failed" in result.output
        assert not journal.exists()

    def test_session_survives_a_reconnect_epoch(
        self, journal: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runner = CliRunner()
        self._patch_context(
            monkeypatch,
            _unrestricted(),
            _unrestricted(),
            session=_fixture_session(),
            snapshot=_fixture_snapshot(),
        )
        first = _watch(runner, journal, "--target", "KITENGELA@10", "--gateway-status", "--authorized")
        assert first.exit_code == 0, first.output

        self._patch_context(monkeypatch, _unrestricted(), snapshot=_fixture_snapshot())
        second = _watch(runner, journal, "--reconnect", "--authorized")
        assert second.exit_code == 0, second.output

        stored = json.loads(journal.read_text(encoding="utf-8"))
        assert stored["samples"][1]["epoch"] == 1
        assert stored["samples"][1]["gateway_session"] is None
