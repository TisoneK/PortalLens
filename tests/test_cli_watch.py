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

UNRESTRICTED_BODY = "Microsoft NCSI"
PORTAL_URL = "http://maz.wifi/login?dst=http%3A%2F%2Fwww.msftconnecttest.com%2Fredirect"


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
