"""Tests for the TUI surface (ADR-7).

Covers the binding invariants from ADR-7:

- Importing ``portallens`` core does **not** pull Textual — the TUI is
  an optional extra. A script doing ``from portallens import ...`` must
  not pay textual's import cost.
- The TUI contains no analysis logic — it renders a ``PortalReport``
  it was handed.
- No vendor hostname is baked into any screen — ``maz.wifi`` and
  ``captive.ispman.tech`` appear only via the report's evidence.
- Severity/status are never colour-only — every confidence badge
  carries its label text alongside the percentage.
- The relationship view's layout swaps at the width threshold.

The textual-dependent tests use Textual's ``run_test`` harness, which
renders the app to an off-screen pilot. They do not require a real
terminal. pytest-asyncio provides the event loop.
"""

from __future__ import annotations

import sys

import pytest

from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.portal import AnalysisContext
from portallens.tui.theme import (
    WIDE_THRESHOLD,
    confidence_label_text,
    confidence_markup,
    relationship_kind_label,
)


def _investigation_for(report):
    """Wrap a fresh PortalReport in an Investigation (ADR-8) for the app."""

    from portallens.investigation.models import Investigation

    return Investigation.start(report, portal_type=report.portal_type)


def _make_app(report, **kwargs):
    """Build a PortalLensApp over the report's investigation."""

    from portallens.tui import PortalLensApp

    return PortalLensApp(_investigation_for(report), **kwargs)

# ---------------------------------------------------------------------------
# ADR-7: import boundary — core must not pull textual.
# ---------------------------------------------------------------------------


class TestImportBoundary:
    """The TUI is an optional extra — core never imports textual."""

    def test_core_import_does_not_load_textual(self) -> None:
        # Use a fresh subprocess so sys.modules is clean — the test
        # process itself has already imported textual (these tests
        # import portallens.tui), so we can't check in-process.
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "from portallens import PortalReport, PortalType; "
                    "from portallens.plugins.captive_wifi import CaptiveWifiPortal; "
                    "assert 'textual' not in sys.modules, "
                    "'core import pulled textual!'; "
                    "print('OK')"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"core import pulled textual.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_cli_import_does_not_load_textual(self) -> None:
        # The CLI module itself must also not import textual at module
        # load — the tui subcommand imports it lazily inside the
        # function body.
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "import portallens.cli; "
                    "assert 'textual' not in sys.modules, "
                    "'cli module-load pulled textual!'; "
                    "print('OK')"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"cli module-load pulled textual.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# ADR-7: severity/status never colour-only.
# ---------------------------------------------------------------------------


class TestSeverityNeverColourOnly:
    """Every confidence badge carries its label text, not just colour."""

    @pytest.mark.parametrize(
        "value,label",
        [
            (0, "very_low"),
            (19, "very_low"),
            (20, "low"),
            (39, "low"),
            (40, "medium"),
            (59, "medium"),
            (60, "high"),
            (79, "high"),
            (80, "very_high"),
            (100, "very_high"),
        ],
    )
    def test_markup_contains_label_and_percentage(self, value: int, label: str) -> None:
        markup = confidence_markup(value)
        # The label text MUST appear — colour alone is forbidden.
        assert label in markup, f"markup {markup!r} missing label {label!r}"
        # The percentage MUST appear too.
        assert f"{value}%" in markup, f"markup {markup!r} missing {value}%"

    def test_label_text_has_no_markup(self) -> None:
        # The plain-text form is what a screen reader / log line sees.
        # It must carry the label even if all markup is stripped.
        text = confidence_label_text(35)
        assert "low" in text
        assert "35%" in text
        assert "[" not in text  # no Textual markup brackets

    def test_relationship_kind_label_is_text(self) -> None:
        # Relationship kinds are structural content — never colour-only.
        assert relationship_kind_label("redirects_to") == "redirects to"
        assert relationship_kind_label("uses_platform") == "uses platform"
        # Unknown kinds fall back to a readable form, never blank.
        assert relationship_kind_label("unknown_kind") == "unknown kind"


# ---------------------------------------------------------------------------
# ADR-7: no vendor hostnames baked into TUI screens.
# ---------------------------------------------------------------------------


class TestNoVendorHostnamesBakedIn:
    """``maz.wifi`` and ``captive.ispman.tech`` never appear as literals
    in the TUI source — they come from the report's evidence only.

    The check scans **executable string literals** (via the AST) so
    docstrings and comments — which legitimately reference vendor names
    as examples — don't trip it. Only code that would actually bake a
    vendor hostname into a screen is a violation.
    """

    def test_no_vendor_literals_in_tui_source(self) -> None:
        import ast
        from pathlib import Path

        tui_dir = Path(__file__).resolve().parent.parent / "src" / "portallens" / "tui"
        # Vendor hostnames that must NEVER appear as executable string
        # literals in TUI code. They appear in test fixtures, in the
        # analyzer, and in TUI docstrings/comments as examples — all
        # fine. What's forbidden is a screen hardcoding them as a
        # default, placeholder, or demo value.
        forbidden = ["maz.wifi", "captive.ispman.tech", "ispman.tech", "mikrotik"]
        offenders: list[str] = []
        for py_file in tui_dir.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                # ast.Constant covers str literals; ast.Str is deprecated
                # in 3.8+ but ast.walk still yields Constant for strings.
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    # Skip docstrings — they're documentation, not code.
                    # (ast.get_docstring on the enclosing FunctionDef /
                    # ClassDef / Module marks them; simpler: skip any
                    # Constant that is the first statement of a body.)
                    val = node.value.lower()
                    for needle in forbidden:
                        if needle in val:
                            offenders.append(
                                f"{py_file.name}:{node.lineno}: string literal contains {needle!r}"
                            )
        assert not offenders, (
            "ADR-7 violation: vendor hostnames baked into TUI string literals.\n"
            "Vendor names may appear in docstrings/comments as examples, "
            "but not as executable string literals (defaults, placeholders, "
            "demo values).\nOffenders:\n" + "\n".join(offenders)
        )


# ---------------------------------------------------------------------------
# ADR-7: the TUI is pure presentation — no analysis logic.
# ---------------------------------------------------------------------------


class TestPurePresentation:
    """The TUI app constructs from a PortalReport and renders it — it
    never runs analysis itself."""

    @pytest.fixture
    def report(self):
        from portallens.evidence import reset_evidence_ids

        reset_evidence_ids()
        from tests.data import ISPMAN_URL, MAZ_URL

        portal = CaptiveWifiPortal()
        return portal.analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))

    def test_app_constructs_from_investigation(self, report) -> None:
        app = _make_app(report)
        assert app._investigation.report is report  # holds the report, doesn't recompute it

    def test_app_does_not_re_run_analysis(self, report, monkeypatch) -> None:
        # If the app tried to call analyze() itself, this would catch it.
        called = []

        def fail_analyze(*args, **kwargs):
            called.append("analyze was called")
            raise AssertionError("TUI must not call analyze()")

        monkeypatch.setattr(CaptiveWifiPortal, "analyze", fail_analyze)
        _make_app(report)  # construction alone must not trigger analysis
        assert called == []


# ---------------------------------------------------------------------------
# ADR-7: responsive layout — relationship view swaps at WIDE_THRESHOLD.
# ---------------------------------------------------------------------------


class TestResponsiveness:
    """The relationship view's layout is driven by terminal width."""

    def test_wide_threshold_is_set(self) -> None:
        # ADR-7: "panels reflow and stack rather than assuming width."
        # The threshold must be set to something reasonable for Termux
        # portrait (~40 cols) on the low end.
        assert 60 <= WIDE_THRESHOLD <= 120, (
            f"WIDE_THRESHOLD={WIDE_THRESHOLD} is outside a sane range for "
            "the Termux-to-desktop span ADR-7 calls for"
        )

    @pytest.mark.asyncio
    async def test_narrow_layout_stacks(self) -> None:
        # Below WIDE_THRESHOLD, the relationship view gets the `narrow`
        # class, which stacks tree over detail.
        from portallens.evidence import reset_evidence_ids
        from tests.data import ISPMAN_URL, MAZ_URL

        reset_evidence_ids()
        report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        app = _make_app(report)
        async with app.run_test(size=(WIDE_THRESHOLD - 10, 40)):
            from portallens.tui.widgets import RelationshipView

            rv = app.query_one(RelationshipView)
            assert rv.has_class("narrow"), (
                f"expected `narrow` class at width {WIDE_THRESHOLD - 10}, "
                f"classes={rv.classes}"
            )

    @pytest.mark.asyncio
    async def test_wide_layout_side_by_side(self) -> None:
        # At or above WIDE_THRESHOLD, the relationship view drops the
        # `narrow` class — tree and detail sit side by side.
        from portallens.evidence import reset_evidence_ids
        from tests.data import ISPMAN_URL, MAZ_URL

        reset_evidence_ids()
        report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        app = _make_app(report)
        async with app.run_test(size=(WIDE_THRESHOLD + 20, 40)):
            from portallens.tui.widgets import RelationshipView

            rv = app.query_one(RelationshipView)
            assert not rv.has_class("narrow"), (
                f"expected NO `narrow` class at width {WIDE_THRESHOLD + 20}, "
                f"classes={rv.classes}"
            )


# ---------------------------------------------------------------------------
# ADR-7: the relationship tree is the indented/linear fallback — it
# always renders, never a wide node diagram.
# ---------------------------------------------------------------------------


class TestRelationshipTree:
    """The relationship tree renders the report's relationships as an
    indented list — the narrow-terminal fallback ADR-7 mandates."""

    @pytest.mark.asyncio
    async def test_tree_renders_all_relationships(self) -> None:
        from portallens.evidence import reset_evidence_ids
        from portallens.tui.widgets import RelationshipTree
        from tests.data import ISPMAN_URL, MAZ_URL

        reset_evidence_ids()
        report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        app = _make_app(report)
        async with app.run_test(size=(120, 50)):
            tree = app.query_one(RelationshipTree)
            # The root's children are the relationship-kind groups.
            # Each kind group's children are the relationships of that kind.
            kind_groups = list(tree.root.children)
            assert len(kind_groups) > 0, "tree has no kind-group nodes"

            # Count total leaf relationships across all kind groups.
            total_leaves = sum(len(group.children) for group in kind_groups)
            assert total_leaves == len(report.relationships), (
                f"tree has {total_leaves} relationship leaves, "
                f"report has {len(report.relationships)}"
            )

    @pytest.mark.asyncio
    async def test_selecting_a_node_updates_detail(self) -> None:
        from portallens.evidence import reset_evidence_ids
        from portallens.tui.widgets import RelationshipDetail, RelationshipTree
        from tests.data import ISPMAN_URL, MAZ_URL

        reset_evidence_ids()
        report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))
        app = _make_app(report)
        async with app.run_test(size=(120, 50)) as pilot:
            tree = app.query_one(RelationshipTree)
            detail = app.query_one(RelationshipDetail)

            # Initially the detail pane shows the placeholder.
            assert detail._relationship is None

            # Find the first leaf node that carries a PortalRelationship.
            leaf = None
            for group in tree.root.children:
                for child in group.children:
                    if child.data is not None:
                        leaf = child
                        break
                if leaf is not None:
                    break
            assert leaf is not None, "no relationship leaf node found"

            # Select it — the detail pane should update.
            tree.select_node(leaf)
            await pilot.pause()
            assert detail._relationship is not None
            assert detail._relationship is leaf.data


# ---------------------------------------------------------------------------
# Live console — controls, activity feed, save/export, live recompute.
# These never touch the network: active steps are refused before any
# worker runs (the authorization gate is synchronous), and evidence is
# injected directly.
# ---------------------------------------------------------------------------


class TestLiveConsole:
    """The console issues engine commands from controls and updates live."""

    @pytest.fixture
    def report(self):
        from portallens.evidence import reset_evidence_ids

        reset_evidence_ids()
        from tests.data import ISPMAN_URL, MAZ_URL

        return CaptiveWifiPortal().analyze(AnalysisContext(urls=[ISPMAN_URL, MAZ_URL]))

    def test_controls_are_bound(self, report) -> None:
        app = _make_app(report)
        keys = {b.key for b in app.BINDINGS}
        assert {"n", "p", "m", "a", "s", "e", "r", "q", "1", "2"} <= keys

    def test_next_steps_computed_from_open_questions(self, report) -> None:
        app = _make_app(report)
        slugs = [step.slug for step in app._available_steps()]
        # The fixture's open questions name resolve_dns + ip_asn_lookup.
        assert slugs == ["resolve_dns", "ip_asn_lookup"]

    @pytest.mark.asyncio
    async def test_passive_step_refused_with_hint(self, report, monkeypatch) -> None:
        app = _make_app(report)  # passive by default
        captured: list[str] = []
        monkeypatch.setattr(app, "_feed", lambda markup: captured.append(markup))
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_run_step(0)
            await pilot.pause()
        assert any("requires --authorized" in line for line in captured)

    @pytest.mark.asyncio
    async def test_digit_key_triggers_step_action(self, report, monkeypatch) -> None:
        app = _make_app(report)
        captured: list[str] = []
        monkeypatch.setattr(app, "_feed", lambda markup: captured.append(markup))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("1")
            await pilot.pause()
        assert any("requires --authorized" in line for line in captured)

    @pytest.mark.asyncio
    async def test_status_bar_and_activity_feed_present(self, report) -> None:
        from textual.widgets import RichLog

        from portallens.tui.widgets import StatusBar

        app = _make_app(report)
        async with app.run_test(size=(120, 40)):
            assert app.query_one(StatusBar) is not None
            assert app.query_one(RichLog) is not None
            assert "passive" in str(app.query_one(StatusBar).render())

    @pytest.mark.asyncio
    async def test_save_persists_investigation(self, report, tmp_path) -> None:
        db_path = str(tmp_path / "demo.db")
        app = _make_app(report, db_path=db_path)
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_save()
            await pilot.pause()

        from portallens.investigation import InvestigationStore

        with InvestigationStore(db_path) as store:
            assert store.get(app._investigation.id) is not None

    @pytest.mark.asyncio
    async def test_export_writes_markdown(self, report, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        app = _make_app(report)
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_export()
            await pilot.pause()
        files = list(tmp_path.glob("portallens-report-*.md"))
        assert len(files) == 1
        assert "PortalLens Report" in files[0].read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_applying_evidence_recomputes_and_closes_questions(self, report) -> None:
        from portallens.evidence import Evidence, EvidenceType

        app = _make_app(report)
        async with app.run_test(size=(120, 40)) as pilot:
            before = len(app._investigation.report.evidence)
            app._apply_evidence(
                [
                    Evidence(
                        type=EvidenceType.IP_ASN,
                        source="ip_asn_lookup://captive.ispman.tech",
                        key="asn",
                        value="AS33771",
                        note="upstream ISP identified",
                    )
                ],
                "ip_asn_lookup",
            )
            await pilot.pause()
        updated = app._investigation.report
        assert len(updated.evidence) == before + 1
        # The upstream-ISP open question closes once IP_ASN evidence exists
        # (engine's refine_open_questions — ADR-9 loop closure).
        assert not any(q.kind is not None and q.kind.value == "upstream_of" for q in updated.open_questions)

    @pytest.mark.asyncio
    async def test_monitor_refused_when_passive(self, report, monkeypatch) -> None:
        app = _make_app(report)
        captured: list[str] = []
        monkeypatch.setattr(app, "_feed", lambda markup: captured.append(markup))
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_toggle_monitor()
            await pilot.pause()
        assert not app._monitor_enabled
        assert any("monitor requires --authorized" in line for line in captured)
