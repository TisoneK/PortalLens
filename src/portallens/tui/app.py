"""The PortalLens live investigation-console TUI.

ADR-7: \"The TUI is a pure presentation + control layer. It renders
``PortalReport`` / ``Investigation`` state and issues commands to the
engine; it contains **no** acquisition, fingerprinting, or inference
logic.\"

This app is the **control layer** realized: it holds an
:class:`~portallens.investigation.models.Investigation` (the mutable,
persisted aggregate — ADR-8), renders its report live, and issues engine
commands — registered analysis steps (:mod:`portallens.steps`), the
NetAudit admin-port probe (:mod:`portallens.security.audit`), checks and
open-question refinement — all invoked from the engine, never
re-implemented here.

The engine itself is untouched: the passive analysis that produced the
report is run by the CLI before the app starts (\"step zero\"), and every
action the console performs funnels through the registered step/probe
APIs the CLI ``step`` verb already uses.

Controls (shown live in the Footer):

- ``1``-``9``  run the Nth computed next-step (from the open questions'
  ``resolves_with`` lists — the ADR-9 computed queue).
- ``n``        run the next available step (auto-picked).
- ``p``        run the admin-port probe pass (authorized only).
- ``m``        toggle continuous monitor mode (re-probes on an interval).
- ``a``        toggle auto-run (kicks off the next step when one becomes
  available).
- ``s``        persist the investigation to the SQLite store.
- ``e``        export the current report as Markdown to a file.
- ``r``        re-render all panels from the current report.
- ``q``        quit.

Authorization (ADR-15): the single ``--authorized`` flag the CLI passes
through as ``AcquisitionPolicy.authorized`` unlocks every active action.
Without it, active keys are refused with a feed line — the passive
default stands.

Live updates: actions run in Textual worker threads, results stream into
the activity feed (a :class:`textual.widgets.Log`), the status bar
counters bump, and panels re-render the moment evidence lands. Open
questions that the new evidence answers disappear via the engine's
``refine_open_questions``; findings recompute via ``run_checks``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.timer import Timer
from textual.widgets import Footer, Header, RichLog

from portallens.acquisition import AcquisitionDenied
from portallens.evidence import Evidence, EvidenceType
from portallens.investigation.models import Investigation
from portallens.portal import AcquisitionPolicy, SecurityFinding
from portallens.reporting import render_markdown
from portallens.steps import refine_open_questions
from portallens.steps.registry import AnalysisStep, compute_next_steps, hosts_from_report
from portallens.tui.widgets import (
    EvidencePanel,
    FingerprintPanel,
    ObservationsPanel,
    OpenQuestionsPanel,
    RelationshipTree,
    RelationshipView,
    ReportHeader,
    StatusBar,
)

_MAX_STEP_BINDINGS = 9


class PortalLensApp(App[None]):
    """The live investigation-console TUI.

    Construct with an :class:`Investigation` (already seeded by the
    engine's step-zero analysis) plus the acquisition policy and console
    mode flags. The CLI auto-saves the investigation before the app
    starts; ``s`` re-saves after actions.

    Construction is side-effect free — persistence happens in the CLI
    (or via the ``s`` control), never in the constructor.
    """

    TITLE = "PortalLens"
    SUB_TITLE = "live investigation console"

    BINDINGS: ClassVar = [
        Binding("n", "run_next", "next step"),
        Binding("p", "probe", "admin port probe"),
        Binding("m", "toggle_monitor", "monitor"),
        Binding("a", "toggle_auto", "auto-run"),
        Binding("s", "save", "save investigation"),
        Binding("e", "export", "export report"),
        Binding("r", "refresh", "refresh"),
        Binding("q", "quit", "quit"),
        # Digit keys run the Nth computed next-step (parameterized action).
        *[Binding(str(i), f"run_step({i - 1})", f"run step {i}") for i in range(1, _MAX_STEP_BINDINGS + 1)],
    ]

    CSS = """
    Screen {
        layout: vertical;
    }
    #body {
        height: 1fr;
        padding: 0 1;
    }
    StatusBar {
        height: auto;
        padding: 0 1;
        background: $boost;
        border: round $primary;
    }
    #activity {
        height: 10;
        border: round $accent;
        margin: 1 0 0 0;
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

    def __init__(
        self,
        investigation: Investigation,
        *,
        policy: AcquisitionPolicy | None = None,
        auto_start: bool = False,
        monitor: bool = False,
        monitor_interval: float = 5.0,
        db_path: str | None = None,
    ) -> None:
        """Build the console over ``investigation``.

        ``auto_start`` begins the \"auto-run\" mode immediately (the next
        available step kicks off when one exists). ``monitor`` begins
        continuous probing of admin ports every ``monitor_interval``
        seconds (requires an authorized policy). ``db_path`` is where
        ``s`` persists the investigation.
        """
        super().__init__()
        self._investigation = investigation
        self._policy = policy or AcquisitionPolicy()
        self._auto_run = bool(auto_start)
        self._monitor_requested_at_start = bool(monitor)
        self._monitor_enabled = False
        self._monitor_interval = max(1.0, monitor_interval)
        self._db_path = db_path
        self._busy = False
        self._monitor_timer: Timer | None = None
        self._last_open_ports: set[tuple[str, int]] = set()

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield StatusBar()
        with VerticalScroll(id="body"):
            yield ReportHeader(self._investigation.report)
            yield FingerprintPanel(self._investigation.report)
            yield ObservationsPanel(self._investigation.report)
            yield RelationshipView(self._investigation.report)
            yield EvidencePanel(self._investigation.report)
            yield OpenQuestionsPanel(self._investigation.report)
        yield RichLog(id="activity", wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._feed(
            "PortalLens live console — "
            f"target [bold]{escape(self._investigation.target)}[/bold]"
        )
        self._feed(
            f"{'active' if self._policy.authorized else 'passive'} mode — "
            "n=next step, p=probe, m=monitor, a=auto-run, "
            "s=save, e=export, r=refresh, q=quit"
        )
        steps = self._available_steps()
        if steps:
            queue = ", ".join(
                f"{i}={s.slug}" for i, s in enumerate(steps[:_MAX_STEP_BINDINGS], start=1)
            )
            self._feed(f"next steps: {escape(queue)}")
        else:
            self._feed("[dim]no next steps available[/dim]")
        self._refresh_all()
        if self._monitor_requested_at_start:
            self.action_toggle_monitor()
        if self._auto_run:
            self._schedule_next()

    # ------------------------------------------------------------------
    # Live refresh
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        """Re-render every panel + status bar from the current report."""

        report = self._investigation.report
        self.query_one(StatusBar).render_state(
            report,
            authorized=self._policy.authorized,
            mode=self._mode(),
            busy=self._busy,
        )
        for panel in (
            ReportHeader,
            FingerprintPanel,
            ObservationsPanel,
            EvidencePanel,
            OpenQuestionsPanel,
        ):
            self.query_one(panel).refresh_content()
        self.query_one(RelationshipTree).rebuild()

    def _refresh_status(self) -> None:
        self.query_one(StatusBar).render_state(
            self._investigation.report,
            authorized=self._policy.authorized,
            mode=self._mode(),
            busy=self._busy,
        )

    def _mode(self) -> str:
        if self._monitor_enabled:
            return "monitor"
        if self._auto_run:
            return "auto"
        return "console"

    # ------------------------------------------------------------------
    # Activity feed
    # ------------------------------------------------------------------

    def _feed(self, markup: str) -> None:
        """Append one timestamped line to the live activity feed."""

        stamp = time.strftime("%H:%M:%S")
        self.query_one(RichLog).write(f"[dim]{stamp}[/dim] {markup}\n")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_status()

    # ------------------------------------------------------------------
    # Step bindings — the ADR-9 computed \"next investigation\" queue.
    # ------------------------------------------------------------------

    def _available_steps(self) -> list[AnalysisStep]:
        """The computed next-steps whose evidence is not yet satisfied.

        A step is \"done\" once all of its declared ``produces`` evidence
        types are present in the report — the same evidence-driven idea
        as the engine's open-question closure, so running a step once
        removes it from the queue.
        """

        report = self._investigation.report
        present = {ev.type for ev in report.evidence}
        return [
            step
            for step in compute_next_steps(report.open_questions)
            if not all(t in present for t in step.produces)
        ]

    def action_run_step(self, step_no: int) -> None:
        steps = self._available_steps()
        if step_no >= len(steps):
            self._feed(f"[dim]no next step #{step_no + 1}[/dim]")
            return
        self._run_step(steps[step_no])

    def action_run_next(self) -> None:
        steps = self._available_steps()
        if not steps:
            self._feed("[dim]no next step available[/dim]")
            return
        self._feed(f"next step: [bold]{steps[0].label}[/bold] ({steps[0].slug})")
        self._run_step(steps[0])

    def _run_step(self, step: AnalysisStep) -> None:
        """Run one registered step, refusing synchronously if unauthorized."""

        if self._busy:
            self._feed("[yellow]busy — wait for the current action to finish[/yellow]")
            return
        if step.requires is not None and not self._policy.authorized:
            self._feed(f"[yellow]{step.slug} requires --authorized[/yellow]")
            return
        self._set_busy(True)
        self._feed(f"running [bold]{escape(step.label)}[/bold] ({step.slug}) …")
        self._action_worker(
            lambda: step.run(self._investigation, self._policy),
            label=step.label,
            slug=step.slug,
        )

    # ------------------------------------------------------------------
    # Admin-port probe (NetAudit, authorized only)
    # ------------------------------------------------------------------

    def action_probe(self) -> None:
        if not self._policy.authorized:
            self._feed("[yellow]admin port probe requires --authorized[/yellow]")
            return
        if self._busy:
            self._feed("[yellow]busy — wait for the current action to finish[/yellow]")
            return
        hosts = hosts_from_report(self._investigation.report)
        if not hosts:
            self._feed("[yellow]no hosts in the report to probe[/yellow]")
            return
        self._set_busy(True)
        self._feed(f"probing admin ports on {escape(', '.join(hosts))} …")

        from portallens.security.audit import probe_admin_ports

        self._action_worker(
            lambda: probe_admin_ports(hosts, self._policy),
            label="admin port probe",
            slug="netaudit",
        )

    @work(thread=True, exclusive=True)
    def _action_worker(
        self,
        action: Callable[[], list[Evidence]],
        *,
        label: str,
        slug: str,
        quiet: bool = False,
    ) -> None:
        """Run one engine action in a background worker (single-flight).

        One exclusive worker serves every action, so a step and a probe
        can never overlap — the busy flag is race-free. Any exception
        (not just :class:`AcquisitionDenied`) logs to the feed and
        clears busy, so a failing action can never wedge the console.
        """

        try:
            evidence = action()
        except AcquisitionDenied as exc:
            self.call_from_thread(self._feed, f"[yellow]refused[/yellow] {escape(str(exc))}")
            self.call_from_thread(self._set_busy, False)
            return
        except Exception as exc:
            self.call_from_thread(
                self._feed, f"[red]{escape(label)} failed[/red] {escape(str(exc))}"
            )
            self.call_from_thread(self._set_busy, False)
            return
        if quiet:
            self.call_from_thread(self._apply_evidence, evidence, slug, refresh=False)
        else:
            self.call_from_thread(self._stream_evidence, evidence, slug, label)

    # ------------------------------------------------------------------
    # Evidence handling — append, recompute, re-render (engine calls only)
    # ------------------------------------------------------------------

    def _stream_evidence(
        self, evidence: list[Evidence], step_slug: str, label: str
    ) -> None:
        """Log the evidence records, then apply them to the report."""

        self._feed(f"[bold]{escape(label)}[/bold] produced {len(evidence)} record(s)")
        for ev in evidence:
            value = ev.value if len(ev.value) <= 80 else ev.value[:80] + "…"
            self._feed(f"  [{ev.type.value}] {escape(ev.key)} = {escape(value)}")
        self._apply_evidence(evidence, step_slug)

    def _apply_evidence(
        self, evidence: list[Evidence], step_slug: str, *, refresh: bool = True
    ) -> None:
        """Append deduplicated evidence, recompute, re-render live.

        The recompute uses the engine's own functions — ``run_checks``
        over the enriched evidence and ``refine_open_questions`` to close
        the questions the new evidence answers (ADR-9 loop closure) —
        exactly what the CLI ``step`` verb does. This is the control
        layer issuing engine commands, not analysis logic in the TUI.

        ``refresh=False`` is used by the quiet monitor tick: the full
        re-render is skipped unless new evidence or a port change made
        the screen stale.
        """

        fresh = self._dedupe_evidence(evidence)
        if fresh:
            self._investigation.append_evidence(fresh, step=step_slug)
        report = self._investigation.report
        self._investigation.report = report.model_copy(
            update={
                "findings": _run_checks(report.evidence),
                "open_questions": refine_open_questions(
                    report.open_questions, report.evidence
                ),
            }
        )
        self._set_busy(False)
        changed = self._update_open_ports(evidence) if self._monitor_enabled else False
        if refresh or fresh or changed:
            self._refresh_all()
        if self._auto_run:
            self._schedule_next()

    def _dedupe_evidence(self, evidence: list[Evidence]) -> list[Evidence]:
        """Drop records already present on the report (type, source, key, value).

        Keeps re-running a step (or the monitor re-probing the same
        ports) from inflating the evidence list with duplicates.
        """

        existing = {
            (ev.type, ev.source, ev.key, ev.value) for ev in self._investigation.report.evidence
        }
        return [
            ev for ev in evidence if (ev.type, ev.source, ev.key, ev.value) not in existing
        ]

    def _schedule_next(self) -> None:
        """Auto-run mode: kick off the next available step, if any."""

        if not self._available_steps():
            self._feed("[dim]no next step available[/dim]")
            return
        if not self._policy.authorized:
            self._feed("[yellow]next steps require --authorized[/yellow]")
            return
        self.action_run_next()

    # ------------------------------------------------------------------
    # Continuous monitor mode — re-probe on an interval, log only deltas
    # ------------------------------------------------------------------

    def action_toggle_monitor(self) -> None:
        if self._monitor_enabled:
            self._stop_monitor()
            self._feed("monitor stopped")
            self._refresh_status()
            return
        if not self._policy.authorized:
            self._feed("[yellow]monitor requires --authorized[/yellow] "
                      "(it re-runs the admin port probe)")
            return
        self._monitor_enabled = True
        self._monitor_timer = self.set_interval(
            self._monitor_interval, self._monitor_tick
        )
        self._last_open_ports = set()
        self._feed(
            f"monitor ON — probing admin ports every {self._monitor_interval:g}s"
        )
        self._refresh_status()

    def _stop_monitor(self) -> None:
        self._monitor_enabled = False
        if self._monitor_timer is not None:
            self._monitor_timer.stop()
            self._monitor_timer = None

    def _monitor_tick(self) -> None:
        if self._busy:
            return

        from portallens.security.audit import probe_admin_ports

        hosts = hosts_from_report(self._investigation.report)
        self._action_worker(
            lambda: probe_admin_ports(hosts, self._policy),
            label="admin port probe",
            slug="netaudit",
            quiet=True,
        )

    def _update_open_ports(self, evidence: list[Evidence]) -> bool:
        """Log admin ports that newly opened/closed; True if anything changed."""

        current = {
            (host, port)
            for ev in evidence
            if ev.type is EvidenceType.SERVICE_REACHABLE
            for host, port in _port_pairs(ev)
        }
        new_ports = current - self._last_open_ports
        gone_ports = self._last_open_ports - current
        if not new_ports and not gone_ports:
            return False
        self._last_open_ports = current
        for host, port in sorted(new_ports):
            self._feed(f"[bold green]monitor: port {port} OPEN[/bold green] on {host}")
        for host, port in sorted(gone_ports):
            self._feed(f"[yellow]monitor: port {port} CLOSED[/yellow] on {host}")
        return True

    # ------------------------------------------------------------------
    # Save / export / refresh / quit
    # ------------------------------------------------------------------

    def action_save(self) -> None:
        from portallens.investigation import InvestigationStore

        try:
            with InvestigationStore(self._db_path) as store:
                store.save(self._investigation)
        except Exception as exc:
            self._feed(f"[red]save failed[/red] {escape(str(exc))}")
            return
        self._feed(f"saved investigation [bold]{self._investigation.id}[/bold]")
        self._refresh_status()

    def action_export(self) -> None:
        host = (urlparse(self._investigation.target).hostname or "portal").lower()
        slug = "".join(c if c.isalnum() else "-" for c in host).strip("-") or "portal"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = Path.cwd() / f"portallens-report-{slug}-{stamp}.md"
        try:
            path.write_text(render_markdown(self._investigation.report), encoding="utf-8")
        except OSError as exc:
            self._feed(f"[red]export failed[/red] {escape(str(exc))}")
            return
        self._feed(f"exported report to [bold]{path}[/bold]")

    def action_refresh(self) -> None:
        self._refresh_all()
        self._feed("panels refreshed")

    async def action_quit(self) -> None:
        self.exit()

    def on_unmount(self) -> None:
        self._stop_monitor()


def _run_checks(evidence: list[Evidence]) -> list[SecurityFinding]:
    """Run the SecurityCheck registry over evidence (engine, not TUI)."""

    from portallens.security.checks import run_checks

    return run_checks(evidence)


def _port_pairs(ev: Evidence) -> list[tuple[str, int]]:
    """Parse ``(host, port)`` pairs out of a ``port_scan://host:port`` source."""

    source = ev.source
    if not source.startswith("port_scan://"):
        return []
    remainder = source[len("port_scan://"):]
    host, _, port_text = remainder.rpartition(":")
    if not host or not port_text.isdigit():
        return []
    return [(host, int(port_text))]


__all__ = ["PortalLensApp"]
