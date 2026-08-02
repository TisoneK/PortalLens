"""TUI widgets for PortalLens — pure presentation over :class:`PortalReport`.

This module imports Textual. The :mod:`portallens.tui.__init__` shim
keeps textual out of the import graph of the core library — a script
doing ``from portallens import CaptiveWifiPortal`` never touches this
module. The CLI imports it lazily inside its ``tui`` subcommand.

ADR-7 binding rules these widgets respect:

- **Pure presentation.** No acquisition, fingerprinting, or inference
  logic lives here. The widgets render a :class:`PortalReport` that was
  produced by the engine; they do not modify it.
- **Severity/status never colour-only.** Every confidence badge carries
  its label text alongside its percentage (see :mod:`portallens.tui.theme`).
- **No vendor hostnames baked in.** Vendor hostnames never appear as
  literals in executable code here — they come from the report's
  evidence. A test asserts this (scanning code, not docstrings).
- **Responsive.** The relationship graph's layout swaps from
  side-by-side to stacked below :data:`portallens.tui.theme.WIDE_THRESHOLD`.
"""

from __future__ import annotations

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode

from portallens.portal import PortalRelationship, PortalReport
from portallens.tui.theme import (
    WIDE_THRESHOLD,
    auth_badge,
    confidence_label_text,
    confidence_markup,
    mode_badge,
    observation_heading,
    relationship_kind_label,
)


class _ReportText(Static):
    """Base for the report panels — a :class:`Static` whose content is a
    :class:`rich.text.Text` built from the report.

    Textual 8.x's ``Static.render()`` returns a ``Text``/``Strip``, not a
    bare ``str``. Subclasses implement :meth:`_build_text` and this base
    handles the ``render``/``update`` plumbing.
    """

    def __init__(self, report: PortalReport) -> None:
        super().__init__()
        self._report = report

    def _build_text(self) -> Text:
        raise NotImplementedError

    def render(self) -> Text:
        return self._build_text()

    def on_mount(self) -> None:
        self.update(self._build_text())

    def refresh_content(self) -> None:
        """Re-render this panel from the current report (live update).

        Called by the app after an action appended evidence or otherwise
        changed the report — the panel reflects the new state without
        being recreated.
        """

        self.update(self._build_text())


class StatusBar(Static):
    """The live status line — target, authorization, mode, counters.

    Rendered with the engine's current report state plus the app's
    authorization flag and console mode. Text is the carrier of meaning;
    colour is additive (ADR-7 — never colour alone).
    """

    def __init__(self) -> None:
        super().__init__("")

    def render_state(
        self,
        report: PortalReport,
        authorized: bool,
        mode: str,
        busy: bool,
    ) -> None:
        """Update the line from the live report + console state."""

        busy_mark = " [bold red]RUNNING[/bold red]" if busy else ""
        self.update(
            Text.from_markup(
                f"Target: [bold]{escape(report.primary_url)}[/bold]\n"
                f"{auth_badge(authorized)}  {mode_badge(mode)}  "
                f"[cyan]{len(report.evidence)}[/cyan] evidence · "
                f"[cyan]{len(report.findings)}[/cyan] findings · "
                f"[cyan]{len(report.open_questions)}[/cyan] open questions"
                f"{busy_mark}"
            )
        )


class ReportHeader(_ReportText):
    """One-line summary: primary URL, portal type, strongest fingerprint."""

    def _build_text(self) -> Text:
        r = self._report
        fp = r.strongest_fingerprint()
        fp_part = (
            f"Strongest fingerprint: {fp.platform} "
            f"({confidence_label_text(fp.confidence)})"
            if fp
            else "No platform fingerprint could be derived."
        )
        n_rels = sum(1 for rel in r.relationships if rel.confidence >= 40)
        return Text.from_markup(
            f"[bold]PortalLens[/bold] — {r.portal_type.value.replace('_', ' ').title()}\n"
            f"Primary URL: [dim]{r.primary_url}[/dim]\n"
            f"{fp_part}  ·  {n_rels} relationship(s) >= 40%  ·  "
            f"{len(r.open_questions)} open question(s)"
        )


class EvidencePanel(_ReportText):
    """The captured evidence table, as a scrollable list.

    This is the bottom layer of the report — every inference and
    relationship above cites evidence ids that live here. Keeping it as
    a panel (rather than collapsing it) means a reader can always
    verify a claim by scrolling down to the cited evidence id.
    """

    def _build_text(self) -> Text:
        r = self._report
        lines: list[str] = ["[bold]Captured Evidence[/bold]", ""]
        if not r.evidence:
            lines.append("[dim]No evidence was captured.[/dim]")
            return Text.from_markup("\n".join(lines))
        for ev in r.evidence:
            value = ev.value if len(ev.value) <= 60 else ev.value[:60] + "…"
            lines.append(
                f"[dim]{ev.id}[/dim]  [bold]{ev.type.value}[/bold]  "
                f"[italic]{ev.key}[/italic]  {value}"
            )
        return Text.from_markup("\n".join(lines))


class ObservationsPanel(_ReportText):
    """Facts / inferences / hypotheses, grouped and confidence-badged.

    The order is fixed: facts first (100% — the ground truth), then
    inferences (the calibrated claims), then hypotheses (explicitly
    flagged as requiring verification). A reader scanning top-to-bottom
    moves from established to speculative — same structure as the
    Markdown report.
    """

    def _render_kind(self, kind: str) -> list[str]:
        rows = self._report.observations_of_kind(kind)
        if not rows:
            return []
        heading, style = observation_heading(kind)
        lines = [f"[{style}]{heading}[/{style}]", ""]
        for obs in rows:
            ev_ids = ", ".join(obs.evidence_ids) if obs.evidence_ids else "—"
            lines.append(f"{confidence_markup(obs.confidence)}  {obs.statement}")
            lines.append(f"    [dim]evidence: {ev_ids}[/dim]")
            if obs.note:
                note = obs.note if len(obs.note) <= 100 else obs.note[:100] + "…"
                lines.append(f"    [dim italic]{note}[/dim italic]")
        lines.append("")
        return lines

    def _build_text(self) -> Text:
        lines: list[str] = []
        for kind in ("fact", "inference", "hypothesis"):
            lines.extend(self._render_kind(kind))
        if len(lines) <= 1:
            lines.append("[dim]No observations.[/dim]")
        return Text.from_markup("\n".join(lines))


class RelationshipTree(Tree[object]):
    """The relationship graph — the one screen that genuinely beats Markdown.

    ADR-7: "the relationship graph degrades to an indented/linear form
    below a width threshold." This tree is that indented form. On a wide
    terminal a detail pane sits beside it (see
    :class:`RelationshipView`); on a narrow terminal the detail pane
    stacks below. Either way, the tree itself is always the indented
    form — we never attempt to draw a wide node diagram, which is the
    failure mode ADR-7 rules out.

    The tree's root is the portal's primary host. Children are the
    entities it relates to, grouped by relationship kind. Selecting a
    node posts a message carrying the relationship, which the detail
    pane listens for.

    The tree's data type is ``object`` because kind-group nodes carry
    ``None`` and leaf nodes carry a :class:`PortalRelationship`. A
    tighter type would require a sum type or ``Optional[...]``; ``object``
    is honest and the consumer (:meth:`on_tree_node_selected` in
    :class:`RelationshipView`) narrows at read time.
    """

    def __init__(self, report: PortalReport) -> None:
        super().__init__(label="relationships", data=None)
        self._report = report
        self.show_root = True

    def on_mount(self) -> None:
        self._populate()

    def rebuild(self) -> None:
        """Rebuild the tree from the current report (live update)."""

        self.clear()
        self._populate()

    def _populate(self) -> None:
        from urllib.parse import urlparse

        r = self._report
        root_host = (urlparse(r.primary_url).hostname or r.primary_url).lower()
        self.root.set_label(Text.from_markup(f"[bold]{root_host}[/bold]"))

        # Group relationships by kind so the tree reads top-to-bottom as
        # "this host redirects to …, uses …, is operated by …".
        by_kind: dict[str, list[PortalRelationship]] = {}
        for rel in r.relationships:
            by_kind.setdefault(rel.kind.value, []).append(rel)

        for kind_value in sorted(by_kind.keys()):
            kind_label = relationship_kind_label(kind_value)
            kind_node: TreeNode[object] = self.root.add(
                label=Text.from_markup(f"[italic]{kind_label}[/italic]"),
                data=None,
            )
            for rel in sorted(by_kind[kind_value], key=lambda x: -x.confidence):
                kind_node.add(
                    label=Text.from_markup(
                        f"{confidence_markup(rel.confidence)}  "
                        f"[bold]{rel.other}[/bold]"
                    ),
                    data=rel,
                )
            kind_node.expand()
        self.root.expand()


class RelationshipDetail(Static):
    """The detail pane for the selected relationship.

    Shows the full relationship note and the evidence ids it rests on.
    Updates when the user selects a node in :class:`RelationshipTree`.
    """

    def __init__(self) -> None:
        super().__init__()
        self._relationship: PortalRelationship | None = None

    def show_relationship(self, rel: PortalRelationship | None) -> None:
        self._relationship = rel
        self.update(self._build_text())

    def _build_text(self) -> Text:
        rel = self._relationship
        if rel is None:
            return Text.from_markup(
                "[dim]Select a relationship to see its detail.\n\n"
                "Each relationship cites the evidence ids it rests on — "
                "the confidence score is only as good as that evidence.[/dim]"
            )
        ev_ids = ", ".join(rel.evidence_ids) if rel.evidence_ids else "—"
        lines = [
            f"[bold]{relationship_kind_label(rel.kind.value)}[/bold]",
            f"{confidence_markup(rel.confidence)}  [bold]{rel.other}[/bold]",
            "",
            f"[dim]evidence: {ev_ids}[/dim]",
        ]
        if rel.note:
            lines.append("")
            lines.append(rel.note)
        return Text.from_markup("\n".join(lines))

    def render(self) -> Text:
        return self._build_text()

    def on_mount(self) -> None:
        self.update(self._build_text())


class RelationshipView(Horizontal):
    """Relationship tree + detail pane, responsive to terminal width.

    Below :data:`~portallens.tui.theme.WIDE_THRESHOLD` the tree and
    detail stack vertically (via the ``narrow`` class); at or above it
    they sit side by side. The swap is driven by :meth:`on_resize` —
    the layout is computed from the live terminal width, never assumed.
    """

    DEFAULT_CSS = """
    RelationshipView {
        height: 1fr;
    }
    RelationshipView > VerticalScroll {
        width: 1fr;
        height: 1fr;
        border: round $primary;
        padding: 0 1;
    }
    RelationshipView RelationshipDetail {
        width: 1fr;
        height: 1fr;
        border: round $accent;
        padding: 0 1;
    }
    RelationshipView.narrow {
        layout: vertical;
    }
    RelationshipView.narrow > VerticalScroll {
        height: 1fr;
    }
    RelationshipView.narrow RelationshipDetail {
        height: 1fr;
    }
    """

    def __init__(self, report: PortalReport) -> None:
        super().__init__()
        self._report = report

    def compose(self) -> ComposeResult:
        # The tree goes inside a VerticalScroll so long relationship
        # lists don't get clipped on short terminals.
        with VerticalScroll():
            yield RelationshipTree(self._report)
        yield RelationshipDetail()

    def on_mount(self) -> None:
        self._apply_layout(self.size.width)

    def on_resize(self, event) -> None:  # type: ignore[no-untyped-def]
        self._apply_layout(event.size.width)

    def _apply_layout(self, width: int) -> None:
        """Toggle the ``narrow`` class based on terminal width."""

        if width < WIDE_THRESHOLD:
            self.add_class("narrow")
        else:
            self.remove_class("narrow")

    def on_tree_node_selected(self, event: Tree.NodeSelected[object]) -> None:
        # Only react to nodes that carry a PortalRelationship as data.
        # Kind-group nodes have data=None; the root has data=None too.
        # The tree is typed Tree[object] (kind nodes carry None, leaves
        # carry PortalRelationship), so we narrow here.
        rel = event.node.data
        if rel is None:
            return
        assert isinstance(rel, PortalRelationship)
        detail = self.query_one(RelationshipDetail)
        detail.show_relationship(rel)


class OpenQuestionsPanel(_ReportText):
    """The open questions — gaps the evidence can't close.

    Each question now carries the analysis steps that could resolve it
    (ADR-9's structured ``OpenQuestion``), shown here as a ``next:`` hint.
    The TUI doesn't yet *run* those steps — the analysis-step registry is a
    later slice — but the hint is the seam a future "next investigation"
    action will hang off.
    """

    def _build_text(self) -> Text:
        r = self._report
        lines = ["[bold yellow]Open Questions[/bold yellow]", ""]
        if not r.open_questions:
            lines.append("[dim]No open questions — analysis is complete.[/dim]")
            return Text.from_markup("\n".join(lines))
        lines.append(
            "[dim]Gaps the analyzer could not close with the supplied "
            "evidence. Resolving them needs more input (HTML captures, "
            "DNS records) or an explicitly authorized active assessment.[/dim]"
        )
        lines.append("")
        for q in r.open_questions:
            # Escape the question text — it may contain characters Rich would
            # otherwise parse as markup. (The badge-escaping lesson from the
            # session-4 TUI work.)
            lines.append(f"  • {escape(q.question)}")
            if q.resolves_with:
                lines.append(f"    [dim]next: {escape(', '.join(q.resolves_with))}[/dim]")
        return Text.from_markup("\n".join(lines))


class FingerprintPanel(_ReportText):
    """Platform fingerprints — the detected platforms, ranked by confidence."""

    def _build_text(self) -> Text:
        r = self._report
        lines = ["[bold]Platform Fingerprints[/bold]", ""]
        if not r.fingerprints:
            lines.append("[dim]No platform fingerprint could be derived.[/dim]")
            return Text.from_markup("\n".join(lines))
        for fp in sorted(r.fingerprints, key=lambda f: -f.confidence):
            version = f" [dim]{fp.version}[/dim]" if fp.version else ""
            lines.append(
                f"{confidence_markup(fp.confidence)}  [bold]{fp.platform}[/bold]{version}"
            )
            if fp.note:
                note = fp.note if len(fp.note) <= 100 else fp.note[:100] + "…"
                lines.append(f"    [dim italic]{note}[/dim italic]")
        return Text.from_markup("\n".join(lines))


__all__ = [
    "EvidencePanel",
    "FingerprintPanel",
    "ObservationsPanel",
    "OpenQuestionsPanel",
    "RelationshipDetail",
    "RelationshipTree",
    "RelationshipView",
    "ReportHeader",
]
