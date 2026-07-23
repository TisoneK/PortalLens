"""SQLite persistence for :class:`Investigation` (ADR-8).

ADR-8 chose SQLite over JSON-on-disk for two reasons: DisclosureDesk will need
to query investigations (by target, by disclosure state, by date), and
disclosure-state transitions want to be transactional. This module is that
store.

Storage model
-------------
Each investigation is one row. The queryable facts — id, target, portal type,
timestamps — are promoted to their own columns and indexed; the full aggregate
(including the still-evolving evidence graph) is kept as a JSON document in a
``data`` column. This is a deliberate document-in-SQLite design, not a failure
to normalize: the report's shape is still changing (structured open questions
and analysis steps are coming), and a brittle relational schema for it now
would cost more than it buys. The promoted columns give DisclosureDesk the
queries it needs; the JSON gives the aggregate room to evolve. When a query
need arises that the columns can't serve, the fix is a migration that promotes
another column — which is exactly what the migration ledger below exists for.

Migrations
----------
Schema version lives in SQLite's own ``PRAGMA user_version``. Migrations are an
ordered list applied on connect; a fresh database and an old one both converge
by running every migration past their current version. There is a real ledger
from day one (ADR-8), so v2 is an append, never a rewrite.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType

from portallens.investigation.models import Investigation
from portallens.portal import PortalType

#: The in-memory database sentinel SQLite understands.
MEMORY = ":memory:"


@dataclass(frozen=True)
class InvestigationSummary:
    """A lightweight row for listings — no report payload loaded.

    Everything here comes from a promoted column, so listing many
    investigations never deserializes their JSON.
    """

    id: str
    target: str
    portal_type: PortalType
    created_at: datetime
    updated_at: datetime


def resolve_db_path(explicit: str | os.PathLike[str] | None) -> str:
    """Decide where the database lives.

    Precedence: an explicit path (including ``":memory:"``) →
    ``$PORTALLENS_DB`` → ``$XDG_DATA_HOME/portallens/investigations.db`` →
    ``~/.local/share/portallens/investigations.db``.
    """

    if explicit is not None:
        return str(explicit)
    env = os.environ.get("PORTALLENS_DB")
    if env:
        return env
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return str(base / "portallens" / "investigations.db")


# ---------------------------------------------------------------------------
# Migrations — an ordered ledger. Index i is the migration to schema version
# i + 1. Never edit a shipped migration; append a new one.
# ---------------------------------------------------------------------------

def _migrate_to_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE investigations (
            id          TEXT PRIMARY KEY,
            target      TEXT NOT NULL,
            portal_type TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            data        TEXT NOT NULL
        );
        CREATE INDEX idx_investigations_target  ON investigations(target);
        CREATE INDEX idx_investigations_updated ON investigations(updated_at);
        """
    )


_MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [
    _migrate_to_v1,
]

SCHEMA_VERSION: int = len(_MIGRATIONS)


class InvestigationStore:
    """A SQLite-backed repository of :class:`Investigation` records.

    Usable as a context manager::

        with InvestigationStore() as store:
            store.save(inv)

    Opening the store applies any pending migrations. Writes are committed
    per call — each ``save``/``delete`` is its own transaction.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.database = resolve_db_path(path)
        if self.database != MEMORY:
            Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.database)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        current = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        for version in range(current, len(_MIGRATIONS)):
            _MIGRATIONS[version](self._conn)
            # PRAGMA doesn't accept bound parameters — the value is a trusted
            # integer from our own ledger, never user input.
            self._conn.execute(f"PRAGMA user_version = {version + 1}")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> InvestigationStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def save(self, investigation: Investigation) -> None:
        """Insert or update an investigation (keyed on its id)."""

        self._conn.execute(
            """
            INSERT INTO investigations (id, target, portal_type, created_at, updated_at, data)
            VALUES (:id, :target, :portal_type, :created_at, :updated_at, :data)
            ON CONFLICT(id) DO UPDATE SET
                target      = excluded.target,
                portal_type = excluded.portal_type,
                updated_at  = excluded.updated_at,
                data        = excluded.data
            """,
            {
                "id": investigation.id,
                "target": investigation.target,
                "portal_type": investigation.portal_type.value,
                "created_at": investigation.created_at.isoformat(),
                "updated_at": investigation.updated_at.isoformat(),
                "data": investigation.model_dump_json(),
            },
        )
        self._conn.commit()

    def delete(self, investigation_id: str) -> bool:
        """Delete an investigation. Returns True iff a row was removed."""

        cur = self._conn.execute("DELETE FROM investigations WHERE id = ?", (investigation_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, investigation_id: str) -> Investigation | None:
        """Load one investigation by id, or ``None`` if absent."""

        row = self._conn.execute(
            "SELECT data FROM investigations WHERE id = ?", (investigation_id,)
        ).fetchone()
        if row is None:
            return None
        return Investigation.model_validate_json(row["data"])

    def list(self) -> list[InvestigationSummary]:
        """Summaries of every stored investigation, newest first.

        Reads only promoted columns — no JSON payload is deserialized.
        """

        rows = self._conn.execute(
            """
            SELECT id, target, portal_type, created_at, updated_at
            FROM investigations
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [
            InvestigationSummary(
                id=row["id"],
                target=row["target"],
                portal_type=PortalType(row["portal_type"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    def count(self) -> int:
        """How many investigations are stored."""

        return int(self._conn.execute("SELECT COUNT(*) FROM investigations").fetchone()[0])
