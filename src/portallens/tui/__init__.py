"""PortalLens investigation-console TUI (ADR-7).

This package is the TUI surface described in ADR-7. It is a **pure
presentation + control layer** over the engine — it renders
:class:`~portallens.portal.PortalReport` state and contains no
acquisition, fingerprinting, or inference logic.

**Optional dependency boundary (ADR-7 consequence):** importing this
package imports Textual. A script doing
``from portallens import CaptiveWifiPortal`` must not pull Textual, so
:mod:`portallens.__init__` does **not** import this package. The CLI
imports it lazily, inside its ``tui`` subcommand only.

The TUI is installed behind the ``portallens[tui]`` extra::

    pip install -e ".[tui]"

Without the extra, ``import portallens.tui`` raises a clear
:class:`ImportError` from Textual rather than a confusing module-not-found.
"""

from __future__ import annotations

from portallens.tui.app import PortalLensApp
from portallens.tui.theme import (
    WIDE_THRESHOLD,
    confidence_label_text,
    confidence_markup,
    relationship_kind_label,
)
from portallens.tui.widgets import (
    EvidencePanel,
    FingerprintPanel,
    ObservationsPanel,
    OpenQuestionsPanel,
    RelationshipDetail,
    RelationshipTree,
    RelationshipView,
    ReportHeader,
)

__all__ = [
    "WIDE_THRESHOLD",
    "EvidencePanel",
    "FingerprintPanel",
    "ObservationsPanel",
    "OpenQuestionsPanel",
    "PortalLensApp",
    "RelationshipDetail",
    "RelationshipTree",
    "RelationshipView",
    "ReportHeader",
    "confidence_label_text",
    "confidence_markup",
    "relationship_kind_label",
]
