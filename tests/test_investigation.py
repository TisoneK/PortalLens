"""Tests for the Investigation aggregate and its SQLite store (ADR-8)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from portallens.evidence import reset_evidence_ids
from portallens.investigation import (
    MEMORY,
    SCHEMA_VERSION,
    Investigation,
    InvestigationStore,
    resolve_db_path,
)
from portallens.investigation.store import _MIGRATIONS
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.portal import AnalysisContext, PortalReport, PortalType
from tests.data import ISPMAN_URL, MAZ_URL


def _report() -> PortalReport:
    reset_evidence_ids()
    return CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))


def _investigation() -> Investigation:
    return Investigation.start(_report(), portal_type=PortalType.CAPTIVE_WIFI)


# ---------------------------------------------------------------------------
# The aggregate
# ---------------------------------------------------------------------------


class TestInvestigationModel:
    def test_start_stamps_timestamps(self) -> None:
        inv = _investigation()
        assert isinstance(inv.created_at, datetime)
        assert inv.created_at.tzinfo is not None  # timezone-aware
        assert inv.updated_at >= inv.created_at

    def test_start_opens_the_audit_log(self) -> None:
        inv = _investigation()
        assert len(inv.audit_log) == 1
        assert inv.audit_log[0].kind == "created"

    def test_id_is_derived_from_the_target_host(self) -> None:
        inv = _investigation()
        # Target host is captive.ispman.tech — the id slug reflects the actual
        # target, not a hardcoded example.
        assert inv.id.startswith("captive-ispman-tech-")

    def test_ids_are_unique_across_revisits(self) -> None:
        assert _investigation().id != _investigation().id

    def test_record_appends_audit_entry_and_bumps_updated_at(self) -> None:
        # ADR-15 removed the per-technique authorize() machinery; the audit
        # log is the record of what happened, and record() is how it grows.
        inv = _investigation()
        original = inv.updated_at
        before = len(inv.audit_log)
        inv.record("step", "Analysis step 'resolve_dns' ran under the single authorization flag.")
        assert len(inv.audit_log) == before + 1
        assert inv.audit_log[-1].kind == "step"
        assert inv.updated_at >= original


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


class TestInvestigationStore:
    def test_save_and_get_round_trip_preserves_the_full_report(self, tmp_path: Path) -> None:
        inv = _investigation()
        with InvestigationStore(tmp_path / "db.sqlite") as store:
            store.save(inv)
            loaded = store.get(inv.id)
        assert loaded is not None
        # The whole evidence graph survives the JSON round trip.
        assert loaded.report.model_dump() == inv.report.model_dump()
        assert loaded.id == inv.id
        assert loaded.target == inv.target

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        with InvestigationStore(tmp_path / "db.sqlite") as store:
            assert store.get("nope") is None

    def test_persists_across_store_instances(self, tmp_path: Path) -> None:
        # This is the point of persistence: a second connection (a stand-in
        # for a second process) sees what the first wrote.
        db = tmp_path / "db.sqlite"
        inv = _investigation()
        with InvestigationStore(db) as writer:
            writer.save(inv)
        with InvestigationStore(db) as reader:
            assert reader.get(inv.id) is not None
            assert reader.count() == 1

    def test_save_is_upsert(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        inv = _investigation()
        with InvestigationStore(db) as store:
            store.save(inv)
            inv.record("step", "appended evidence")
            store.save(inv)
            assert store.count() == 1
            reloaded = store.get(inv.id)
            assert reloaded is not None
            assert reloaded.audit_log[-1].detail == "appended evidence"

    def test_list_is_newest_first(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        first = _investigation()
        second = _investigation()
        second.record("touch", "make second newer")
        with InvestigationStore(db) as store:
            store.save(first)
            store.save(second)
            ids = [s.id for s in store.list()]
        assert ids[0] == second.id

    def test_list_reads_only_columns(self, tmp_path: Path) -> None:
        inv = _investigation()
        with InvestigationStore(tmp_path / "db.sqlite") as store:
            store.save(inv)
            summaries = store.list()
        assert len(summaries) == 1
        assert summaries[0].target == inv.target
        assert summaries[0].portal_type is PortalType.CAPTIVE_WIFI

    def test_delete(self, tmp_path: Path) -> None:
        inv = _investigation()
        with InvestigationStore(tmp_path / "db.sqlite") as store:
            store.save(inv)
            assert store.delete(inv.id) is True
            assert store.delete(inv.id) is False  # already gone
            assert store.count() == 0

    def test_memory_database_works(self) -> None:
        inv = _investigation()
        with InvestigationStore(MEMORY) as store:
            store.save(inv)
            assert store.get(inv.id) is not None


class TestMigrations:
    def test_fresh_database_is_at_current_schema_version(self, tmp_path: Path) -> None:
        db = tmp_path / "db.sqlite"
        with InvestigationStore(db) as store:
            version = store._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
        assert len(_MIGRATIONS) == SCHEMA_VERSION

    def test_reopening_is_idempotent(self, tmp_path: Path) -> None:
        # Opening an already-migrated database must not re-run migrations
        # (a re-run of _migrate_to_v1 would fail — the table already exists).
        db = tmp_path / "db.sqlite"
        InvestigationStore(db).close()
        # Second open would raise if migrations re-ran; it must not.
        store = InvestigationStore(db)
        version = store._conn.execute("PRAGMA user_version").fetchone()[0]
        store.close()
        assert version == SCHEMA_VERSION


class TestDbPathResolution:
    def test_explicit_wins(self) -> None:
        assert resolve_db_path("/tmp/x.db") == "/tmp/x.db"

    def test_memory_passes_through(self) -> None:
        assert resolve_db_path(MEMORY) == MEMORY

    def test_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORTALLENS_DB", "/data/inv.db")
        assert resolve_db_path(None) == "/data/inv.db"

    def test_xdg_data_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PORTALLENS_DB", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", "/xdg")
        # Build the expectation the way resolve_db_path does, so the assertion
        # is OS-native — a hardcoded "/"-joined string fails on Windows, where
        # str(Path(...)) uses "\" (found by Session 6 / GitHub Copilot on Windows).
        assert resolve_db_path(None) == str(Path("/xdg") / "portallens" / "investigations.db")

    def test_default_under_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PORTALLENS_DB", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/tester")))
        assert resolve_db_path(None) == str(
            Path("/home/tester") / ".local" / "share" / "portallens" / "investigations.db"
        )
