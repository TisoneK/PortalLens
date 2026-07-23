"""Investigation — PortalLens's persisted unit of work (ADR-8).

An :class:`Investigation` bundles a target, the :class:`~portallens.portal.PortalReport`
produced for it, a per-technique authorization record (ADR-10), and an
append-only audit log, and persists them via :class:`InvestigationStore`
(SQLite). It is the shared foundation for the TUI and the future DisclosureDesk.
"""

from __future__ import annotations

from portallens.investigation.models import (
    ACTIVE_TECHNIQUES,
    AuditEntry,
    AuthorizationGrant,
    Investigation,
)
from portallens.investigation.store import (
    MEMORY,
    SCHEMA_VERSION,
    InvestigationStore,
    InvestigationSummary,
    resolve_db_path,
)

__all__ = [
    "ACTIVE_TECHNIQUES",
    "MEMORY",
    "SCHEMA_VERSION",
    "AuditEntry",
    "AuthorizationGrant",
    "Investigation",
    "InvestigationStore",
    "InvestigationSummary",
    "resolve_db_path",
]
