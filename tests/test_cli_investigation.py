"""CLI-level tests for the investigation subcommands (ADR-8).

These drive the real Click commands through CliRunner against a temp
database, so they cover the wiring `test_investigation.py` doesn't:
argument parsing, exit codes, and the default-subcommand group.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from portallens.cli import main
from tests.data import ISPMAN_URL, MAZ_URL


def _investigate(runner: CliRunner, db: Path) -> str:
    result = runner.invoke(main, ["investigate", "--db", str(db), ISPMAN_URL, MAZ_URL])
    assert result.exit_code == 0, result.output
    # "Investigation saved: <id>"
    line = next(ln for ln in result.output.splitlines() if ln.startswith("Investigation saved:"))
    return line.split(":", 1)[1].strip()


class TestInvestigateCommand:
    def test_creates_and_reports_id(self, tmp_path: Path) -> None:
        runner = CliRunner()
        inv_id = _investigate(runner, tmp_path / "db.sqlite")
        assert inv_id.startswith("captive-ispman-tech-")

    def test_persists_for_a_later_invocation(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)
        # Fresh invocation — the file is the only shared state.
        listing = runner.invoke(main, ["investigations", "--db", str(db)])
        assert listing.exit_code == 0
        assert inv_id in listing.output


class TestShowCommand:
    def test_renders_the_stored_report(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)
        result = runner.invoke(main, ["show", "--db", str(db), inv_id])
        assert result.exit_code == 0
        assert "# PortalLens Report" in result.output
        assert "ISPMan" in result.output

    def test_audit_flag_shows_the_trail(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)
        result = runner.invoke(main, ["show", "--db", str(db), inv_id, "--audit"])
        assert result.exit_code == 0
        assert "Audit trail" in result.output
        assert "created" in result.output

    def test_missing_id_exits_1(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(main, ["show", "--db", str(tmp_path / "db.sqlite"), "nope"])
        assert result.exit_code == 1


class TestAuthorizeCommand:
    def test_records_authorization(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)
        result = runner.invoke(
            main, ["authorize", "--db", str(db), inv_id, "--technique", "resolve_dns", "--note", "ok"]
        )
        assert result.exit_code == 0
        # It shows up in the audit trail from a later invocation.
        audit = runner.invoke(main, ["show", "--db", str(db), inv_id, "--audit"])
        assert "resolve_dns" in audit.output

    def test_unknown_technique_exits_2(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)
        result = runner.invoke(main, ["authorize", "--db", str(db), inv_id, "--technique", "nonsense"])
        assert result.exit_code == 2
        assert "unknown active technique" in result.output

    def test_missing_id_exits_1(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(
            main, ["authorize", "--db", str(tmp_path / "db.sqlite"), "nope", "--technique", "resolve_dns"]
        )
        assert result.exit_code == 1


class TestEmptyListing:
    def test_empty_database_message(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(main, ["investigations", "--db", str(tmp_path / "db.sqlite")])
        assert result.exit_code == 0
        assert "No investigations saved yet" in result.output


class TestStepCommand:
    """The `portallens step <id> <slug>` verb (ADR-9): load -> check
    authorization -> run -> append evidence -> save."""

    def test_unknown_step_exits_2(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)
        result = runner.invoke(main, ["step", "--db", str(db), inv_id, "nonsense"])
        assert result.exit_code == 2
        assert "Unknown analysis step" in result.output

    def test_missing_id_exits_1(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(main, ["step", "--db", str(tmp_path / "db.sqlite"), "nope", "resolve_dns"])
        assert result.exit_code == 1

    def test_requires_authorization_exits_2(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)
        result = runner.invoke(main, ["step", "--db", str(db), inv_id, "resolve_dns"])
        assert result.exit_code == 2
        assert "requires authorization" in result.output

    def test_runs_authorized_step_and_saves(self, tmp_path: Path, monkeypatch) -> None:
        from portallens.steps import dns as dns_mod

        monkeypatch.setattr(dns_mod, "resolve_host", lambda host: ["192.0.2.1"])
        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)
        runner.invoke(main, ["authorize", "--db", str(db), inv_id, "--technique", "resolve_dns"])
        result = runner.invoke(main, ["step", "--db", str(db), inv_id, "resolve_dns"])
        assert result.exit_code == 0, result.output
        assert "produced 2 evidence record(s)" in result.output  # one per observed host
        # The evidence persists: the audit trail now records the step.
        audit = runner.invoke(main, ["show", "--db", str(db), inv_id, "--audit"])
        assert "Analysis step 'resolve_dns'" in audit.output

    def test_unknown_technique_authorization_still_rejected(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)
        # Authorizing an unrelated technique does not authorize resolve_dns.
        runner.invoke(main, ["authorize", "--db", str(db), inv_id, "--technique", "port_scan"])
        result = runner.invoke(main, ["step", "--db", str(db), inv_id, "resolve_dns"])
        assert result.exit_code == 2

    def test_thread_loop_closes_the_upstream_question(self, tmp_path: Path, monkeypatch) -> None:
        """ADR-9 loop closure end-to-end: resolve_dns + ip_asn_lookup answer
        "who's upstream?", and the persisted report stops asking it."""

        from portallens.steps import dns as dns_mod
        from portallens.steps import ip_asn as ip_asn_mod

        monkeypatch.setattr(dns_mod, "resolve_host", lambda host: ["192.0.2.1"])
        monkeypatch.setattr(ip_asn_mod, "whois_for_ip", lambda ip: [("asn", "AS64500")])
        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)

        # The report starts with the upstream question open.
        before = runner.invoke(main, ["show", "--db", str(db), inv_id])
        assert "Who is the upstream Internet bandwidth provider" in before.output

        # Authorize both techniques the thread needs — each explicitly
        # (ADR-13: enabling one never implies another).
        runner.invoke(main, ["authorize", "--db", str(db), inv_id, "--technique", "resolve_dns"])
        runner.invoke(main, ["authorize", "--db", str(db), inv_id, "--technique", "use_osint_apis"])

        # Pull the thread: resolve hostnames, then look up ASN ownership.
        step1 = runner.invoke(main, ["step", "--db", str(db), inv_id, "resolve_dns"])
        assert step1.exit_code == 0, step1.output
        step2 = runner.invoke(main, ["step", "--db", str(db), inv_id, "ip_asn_lookup"])
        assert step2.exit_code == 0, step2.output
        assert "produced" in step2.output

        # The loop closed: the persisted report no longer asks who's upstream.
        after = runner.invoke(main, ["show", "--db", str(db), inv_id])
        assert "Who is the upstream Internet bandwidth provider" not in after.output


class TestFormatOption:
    """`--format sarif` renders findings as SARIF 2.1.0 (reporting/sarif.py)."""

    def test_analyze_sarif_format(self) -> None:
        import json

        runner = CliRunner()
        result = runner.invoke(main, ["analyze", "--format", "sarif", ISPMAN_URL, MAZ_URL])
        assert result.exit_code == 0, result.output
        doc = json.loads(result.output)
        assert doc["version"] == "2.1.0"
        assert doc["runs"][0]["tool"]["driver"]["name"] == "PortalLens"
        assert doc["runs"][0]["results"]  # the fixture carries a fingerprinting finding

    def test_show_sarif_format(self, tmp_path: Path) -> None:
        import json

        db = tmp_path / "db.sqlite"
        runner = CliRunner()
        inv_id = _investigate(runner, db)
        result = runner.invoke(main, ["show", "--db", str(db), inv_id, "--format", "sarif"])
        assert result.exit_code == 0, result.output
        doc = json.loads(result.output)
        assert doc["runs"][0]["results"]

    def test_markdown_is_default(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", ISPMAN_URL, MAZ_URL])
        assert result.exit_code == 0
        assert result.output.startswith("# PortalLens Report")
