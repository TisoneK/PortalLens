"""Tests for the bounded default-credential audit (ADR-26).

No test opens a socket: the login transport is injected, and the telnet
negotiation stripper is exercised against a fake socket.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from portallens.acquisition import AcquisitionDenied
from portallens.cli import main
from portallens.evidence import Evidence, EvidenceType
from portallens.portal import AcquisitionPolicy
from portallens.security.audit import run_netaudit
from portallens.security.checks import run_checks
from portallens.security.credentials import (
    HARD_CREDENTIAL_ATTEMPT_CAP,
    _login_accepted,
    _TelnetStream,
    probe_default_credentials,
)

AUTHORIZED = AcquisitionPolicy(authorized=True)
UNAUTHORIZED = AcquisitionPolicy()

HOST = "10.111.0.1"


class _Recorder:
    """Injected login transport that records what it was asked to try."""

    def __init__(self, accepted: tuple[str, str] | None = None, fail_on: int | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._accepted = accepted
        self._fail_on = fail_on

    def __call__(self, host: str, port: int, username: str, password: str, timeout: float) -> bool:
        self.calls.append((username, password))
        if self._fail_on is not None and len(self.calls) == self._fail_on:
            raise ConnectionResetError("connection reset by peer")
        return self._accepted == (username, password)


class _FakeSock:
    def __init__(self) -> None:
        self.sent = b""

    def sendall(self, data: bytes) -> None:
        self.sent += data


class TestAuthorizationGate:
    def test_requires_the_single_authorization_flag(self) -> None:
        with pytest.raises(AcquisitionDenied):
            probe_default_credentials(HOST, UNAUTHORIZED, login=_Recorder())


class TestBoundedAttempts:
    def test_first_default_accepted_stops_the_audit(self) -> None:
        recorder = _Recorder(accepted=("admin", ""))
        evidence = probe_default_credentials(HOST, AUTHORIZED, login=recorder, attempt_delay=0)

        assert len(recorder.calls) == 1
        assert evidence[0].key == "admin_credential:23"
        assert evidence[0].value == "default_accepted"
        assert "admin/<blank>" in evidence[0].note

    def test_later_default_accepted_is_named(self) -> None:
        recorder = _Recorder(accepted=("admin", "admin"))
        evidence = probe_default_credentials(HOST, AUTHORIZED, login=recorder, attempt_delay=0)

        assert recorder.calls == [("admin", ""), ("admin", "admin")]
        assert evidence[0].value == "default_accepted"
        assert "admin/admin" in evidence[0].note

    def test_all_rejected_records_negative_evidence(self) -> None:
        recorder = _Recorder()
        evidence = probe_default_credentials(HOST, AUTHORIZED, login=recorder, attempt_delay=0)

        assert len(recorder.calls) == 3
        assert evidence[0].value == "default_rejected"
        assert "all were refused" in evidence[0].note

    def test_attempts_are_capped(self) -> None:
        recorder = _Recorder()
        candidates = tuple(("admin", f"guess{i}") for i in range(10))
        probe_default_credentials(
            HOST,
            AUTHORIZED,
            login=recorder,
            candidates=candidates,
            max_attempts=99,
            attempt_delay=0,
        )

        assert len(recorder.calls) == HARD_CREDENTIAL_ATTEMPT_CAP

    def test_transport_failure_stops_before_a_lockout(self) -> None:
        recorder = _Recorder(fail_on=2)
        evidence = probe_default_credentials(HOST, AUTHORIZED, login=recorder, attempt_delay=0)

        assert len(recorder.calls) == 2
        assert evidence[0].value == "default_rejected"
        assert "unreachable" in evidence[0].note


class TestLoginInterpretation:
    def test_routeros_prompt_is_accepted(self) -> None:
        assert _login_accepted("\r\n[admin@MikroTik] > ")

    def test_failure_message_is_not_a_prompt(self) -> None:
        assert not _login_accepted("Login failed, incorrect username or password\r\n\r\nLogin: ")

    def test_empty_reply_is_not_accepted(self) -> None:
        assert not _login_accepted("")

    def test_iac_negotiation_is_stripped_and_answered(self) -> None:
        sock = _FakeSock()
        stream = _TelnetStream(sock)  # type: ignore[arg-type]

        text = stream._strip(b"\xff\xfd\x18\xff\xfb\x01Login: ")

        assert text == "Login: "
        # DO TERMINAL_TYPE -> WONT, WILL ECHO -> DONT
        assert sock.sent == bytes((0xFF, 0xFC, 0x18, 0xFF, 0xFE, 0x01))


class TestAuditWiring:
    def test_port_closed_means_no_credential_attempt(self) -> None:
        recorder = _Recorder(accepted=("admin", ""))
        result = run_netaudit(
            [HOST],
            AUTHORIZED,
            probe_port=lambda host, port: False,
            credential_audit=True,
            credential_login=recorder,
        )

        assert recorder.calls == []
        assert result.evidence == []

    def test_open_telnet_is_audited_only_when_asked(self) -> None:
        recorder = _Recorder(accepted=("admin", ""))
        result = run_netaudit(
            [HOST],
            AUTHORIZED,
            probe_port=lambda host, port: port == 23,
            credential_audit=False,
            credential_login=recorder,
        )

        assert recorder.calls == []
        assert [ev.key for ev in result.evidence] == ["admin_port:23"]
        assert all(f.check_slug != "gateway_admin_default_credential" for f in result.findings)

    def test_accepted_default_raises_the_critical_finding(self) -> None:
        recorder = _Recorder(accepted=("admin", ""))
        result = run_netaudit(
            [HOST],
            AUTHORIZED,
            probe_port=lambda host, port: port == 23,
            credential_audit=True,
            credential_login=recorder,
        )

        assert recorder.calls == [("admin", "")]
        finding = next(
            f for f in result.findings if f.check_slug == "gateway_admin_default_credential"
        )
        assert finding.severity.value == "critical"
        assert finding.confidence >= 90

    def test_rejected_defaults_do_not_raise_the_finding(self) -> None:
        evidence = probe_default_credentials(
            HOST, AUTHORIZED, login=_Recorder(), attempt_delay=0
        )

        assert not [
            f for f in run_checks(evidence) if f.check_slug == "gateway_admin_default_credential"
        ]


class TestCliFlag:
    """The flag is opt-in and reaches the audit; no socket is opened."""

    @staticmethod
    def _patch(monkeypatch: pytest.MonkeyPatch) -> list[list[tuple[str, str, str, str]]]:
        calls: list[list[tuple[str, str, str, str]]] = []

        def fake_ports(hosts: list[str], policy: AcquisitionPolicy, **_: object) -> list[Evidence]:
            return [
                Evidence(
                    type=EvidenceType.SERVICE_REACHABLE,
                    source=f"port_scan://{hosts[0]}:23",
                    key="admin_port:23",
                    value="Telnet (23)",
                )
            ]

        def fake_credentials(
            host: str, policy: AcquisitionPolicy, **kwargs: object
        ) -> list[Evidence]:
            login = kwargs.get("login")
            calls.append([(host, "admin", "", str(login))])
            return [
                Evidence(
                    type=EvidenceType.SERVICE_REACHABLE,
                    source=f"admin_login://{host}:23",
                    key="admin_credential:23",
                    value="default_accepted",
                    note="Port 23 accepted the well-known default login admin/<blank>.",
                )
            ]

        monkeypatch.setattr("portallens.security.audit.probe_admin_ports", fake_ports)
        monkeypatch.setattr("portallens.security.audit.probe_default_credentials", fake_credentials)
        return calls

    def test_flag_runs_the_audit_and_reports_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._patch(monkeypatch)
        result = CliRunner().invoke(
            main,
            ["analyze", "http://maz.wifi/login", "--authorized", "--check-default-credentials"],
        )

        assert result.exit_code == 0, result.output
        assert calls
        assert "well-known default credential" in result.output

    def test_audit_stays_off_without_the_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._patch(monkeypatch)
        result = CliRunner().invoke(main, ["analyze", "http://maz.wifi/login", "--authorized"])

        assert result.exit_code == 0, result.output
        assert calls == []
        assert "well-known default credential" not in result.output
