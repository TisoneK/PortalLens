"""The PortalLens investigation-console TUI app.

ADR-7: "The TUI is a pure presentation + control layer. It renders
``PortalReport`` / ``Investigation`` state and issues commands to the
engine; it contains **no** acquisition, fingerprinting, or inference
logic."

This app composes the widgets from :mod:`portallens.tui.widgets` into a
single screen. It receives a fully-analyzed :class:`PortalReport` at
construction time — it never runs analysis itself. The engine (the
``CaptiveWifiPortal.analyze()`` call that produced the report) is
invoked by the CLI before the app starts.

The layout is a vertical stack of three regions:

1. **Header** — primary URL, portal type, headline counts.
2. **Body** — fingerprints, observations, and the relationship view
   (tree + detail pane, responsive to width).
3. **Footer** — open questions.

The body is a :class:`VerticalScroll`, so on short terminals the whole
report scrolls; on tall terminals everything is visible at once. The
relationship view's internal layout (tree + detail side-by-side vs
stacked) is driven by the terminal width, not the body scroll.

Responsiveness (ADR-7):
- Termux portrait (~40 cols): body scrolls; relationship view stacks
  tree-over-detail (width < :data:`~portallens.tui.theme.WIDE_THRESHOLD`).
- Phone landscape (~80 cols): same — stacked.
- Desktop (>= 120 cols): relationship view shows tree + detail
  side-by-side; body may still scroll if the report is long.

Accessibility (ADR-7):
- Severity/status never colour-only — every confidence badge carries
  its label text alongside its percentage (see :mod:`portallens.tui.theme`).
- All interactive widgets are keyboard-navigable (Textual default).
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header

from portallens.portal import PortalReport
from portallens.tui.widgets import (
    EvidencePanel,
    FingerprintPanel,
    ObservationsPanel,
    OpenQuestionsPanel,
    RelationshipView,
    ReportHeader,
)


class PortalLensApp(App[None]):
    """The investigation-console TUI.

    Construct with a :class:`PortalReport` (already produced by the
    engine) and run with ``await app.run_async()`` (or ``app.run()`` for
    a blocking call). The app does not re-run analysis — it renders the
    report it was given.
    """

    CSS = """
    Screen {
        layout: vertical;
    }
    #body {
        height: 1fr;
        padding: 0 1;
    }
    ReportHeader {
        height: auto;
        padding: 0 1;
        background: $boost;
        border: round $primary;
    }
    EvidencePanel, FingerprintPanel, ObservationsPanel, OpenQuestionsPanel {
        height: auto;
        padding: 0 1;
        margin: 1 0;
    }
    RelationshipView {
        height: auto;
        min-height: 12;
        margin: 1 0;
    }
    """

    TITLE = "PortalLens"
    SUB_TITLE = "investigation console"

    def __init__(self, report: PortalReport) -> None:
        super().__init__()
        self._report = report

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="body"):
            yield ReportHeader(self._report)
            yield FingerprintPanel(self._report)
            yield ObservationsPanel(self._report)
            yield RelationshipView(self._report)
            yield EvidencePanel(self._report)
            yield OpenQuestionsPanel(self._report)
        yield Footer()


__all__ = ["PortalLensApp"]
