"""Investigation — PortalLens's persisted unit of work (ADR-8).

An :class:`Investigation` bundles a target, the :class:`~portallens.portal.PortalReport`
produced for it, and an append-only audit log, and persists them via
:class:`InvestigationStore` (SQLite). It is the shared foundation for the TUI
and the future DisclosureDesk.
"""

from __future__ import annotations

from portallens.investigation.models import AuditEntry, Investigation
from portallens.investigation.store import (
    MEMORY,
    SCHEMA_VERSION,
    InvestigationStore,
    InvestigationSummary,
    resolve_db_path,
)

__all__ = [
    "MEMORY",
    "SCHEMA_VERSION",
    "AuditEntry",
    "Investigation",
    "InvestigationStore",
    "InvestigationSummary",
    "resolve_db_path",
]
