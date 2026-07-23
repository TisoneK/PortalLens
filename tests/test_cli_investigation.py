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
