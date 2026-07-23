"""PortalLens CLI — analyze a portal URL and emit a report.

Two subcommands (ADR-7: "If ``cli.py`` grows a ``tui`` subcommand it
becomes a ``click.Group``; decide that before people script against the
current single-command invocation"):

- ``portallens analyze <urls>...`` — passive (default) analysis,
  prints a Markdown report on stdout. This is the original behaviour.
- ``portallens tui <urls>...`` — runs the same analysis, then opens
  the investigation-console TUI (ADR-7). Requires the ``[tui]`` extra.

**Default-subcommand fallback:** ``portallens <urls>...`` (no subcommand)
still works — it routes to ``analyze``. This preserves the session-1 /
session-2 invocation form that scripts may depend on::

    portallens "http://maz.wifi/login?dst=..." \\
        "https://captive.ispman.tech/hotspots/.../select?..."

Active analysis (``--fetch-urls``, ``--resolve-dns``) requires
``--i-have-authorization`` in both subcommands — ADR-1 is unchanged.

Examples
--------
Passive analysis (default — no network access)::

    portallens "http://maz.wifi/login?dst=..."

TUI on the same URL pair (requires ``pip install -e ".[tui]"``)::

    portallens tui "http://maz.wifi/login?dst=..." \\
        "https://captive.ispman.tech/hotspots/.../select?..."

Active analysis — requires explicit authorization for the target::

    portallens --fetch-urls --i-have-authorization "https://example.com/login"
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

import click

from portallens.plugins.captive_wifi import CaptiveWifiPortal  # noqa: F401 — registers the plugin
from portallens.portal import AcquisitionPolicy, AnalysisContext, PortalReport, PortalType
from portallens.registry import get_portal_class
from portallens.reporting import render_markdown

# ---------------------------------------------------------------------------
# Shared analysis helper — both subcommands run the same engine call.
# The TUI subcommand does NOT re-implement analysis; it calls this and
# hands the resulting PortalReport to the app. This is ADR-7's "pure
# presentation, no analysis logic in the TUI" enforced at the CLI layer.
# ---------------------------------------------------------------------------


def _run_analysis(
    urls: Sequence[str],
    portal_type: str,
    fetch_urls: bool,
    follow_redirects: bool,
    resolve_dns: bool,
    authorization_confirmed: bool,
    notes: str | None,
) -> PortalReport:
    """Run analysis and return the :class:`PortalReport`.

    Shared by both subcommands. Raises :class:`SystemExit` on
    authorization or plugin-lookup failure (after printing a message).
    """

    if not urls:
        click.echo("Error: at least one URL is required.", err=True)
        sys.exit(2)

    # Active-mode guard — require explicit authorization confirmation.
    if (fetch_urls or resolve_dns) and not authorization_confirmed:
        click.echo(
            "Active analysis (--fetch-urls / --resolve-dns) requires explicit "
            "authorization for every URL supplied.\n"
            "Re-run with --i-have-authorization if you have it.",
            err=True,
        )
        sys.exit(2)

    policy = AcquisitionPolicy(
        fetch_urls=fetch_urls,
        follow_redirects=follow_redirects,
        resolve_dns=resolve_dns,
    )

    context = AnalysisContext(
        urls=list(urls),
        policy=policy,
        user_notes=notes,
    )

    ptype = PortalType(portal_type.lower())
    try:
        portal_cls = get_portal_class(ptype)
    except KeyError as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    portal = portal_cls()
    return portal.analyze(context)


# ---------------------------------------------------------------------------
# Common options — applied to both subcommands so the active-analysis
# contract (ADR-1) is identical whether you print Markdown or open the TUI.
# ---------------------------------------------------------------------------

_PORTAL_TYPE_OPTION = click.option(
    "--type",
    "portal_type",
    type=click.Choice([t.value for t in PortalType], case_sensitive=False),
    default=PortalType.CAPTIVE_WIFI.value,
    show_default=True,
    help="Portal type to analyze as. Defaults to captive_wifi — the only implemented plugin today.",
)
_FETCH_OPTION = click.option(
    "--fetch-urls",
    is_flag=True,
    default=False,
    help="Enable active HTTP fetching. Requires --i-have-authorization.",
)
_FOLLOW_REDIRECTS_OPTION = click.option(
    "--follow-redirects",
    is_flag=True,
    default=False,
    help="Follow HTTP redirects when --fetch-urls is set. Off by default.",
)
_RESOLVE_DNS_OPTION = click.option(
    "--resolve-dns",
    is_flag=True,
    default=False,
    help="Enable active DNS resolution. Requires --i-have-authorization.",
)
_AUTH_OPTION = click.option(
    "--i-have-authorization",
    "authorization_confirmed",
    is_flag=True,
    default=False,
    help=(
        "Confirm you have authorization for active analysis of every URL supplied. "
        "Required when --fetch-urls or --resolve-dns is set."
    ),
)
_NOTES_OPTION = click.option(
    "--notes",
    default=None,
    help="Free-text notes to attach to the analysis context (e.g. 'captured from Android Chrome').",
)


class _DefaultAnalyzeGroup(click.Group):
    """A click Group that falls back to `analyze` when the first
    positional arg isn't a known subcommand.

    This preserves the pre-TUI invocation form ``portallens <urls>...``
    that session-1 / session-2 scripts depend on (ADR-7: "decide before
    people script against the current single-command invocation"). A
    URL like ``http://maz.wifi/...`` is not a known subcommand, so it
    routes to ``analyze``; ``portallens tui <urls>...`` still works
    because ``tui`` IS a known subcommand.

    The fallback only triggers when the first arg doesn't match a
    registered subcommand name. ``portallens --help`` and
    ``portallens analyze ...`` are unaffected.
    """

    _DEFAULT = "analyze"

    def resolve_command(self, ctx: click.Context, args: list[str]) -> tuple[str | None, click.Command | None, list[str]]:
        # If the first non-option arg is not a known subcommand, route
        # to the default. This mirrors how `git` falls back to
        # `git commit`-style defaults in some frontends.
        known = set(self.commands) | {"--help", "-h", "--version"}
        # Find the first arg that isn't an option (doesn't start with -).
        # That's the would-be subcommand name.
        for arg in args:
            if not arg.startswith("-"):
                if arg not in known:
                    args = [self._DEFAULT, *args]
                break
        return super().resolve_command(ctx, args)


@click.group(
    cls=_DefaultAnalyzeGroup,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(package_name="portallens")
@click.pass_context
def main(ctx: click.Context) -> None:
    """PortalLens — intelligence and security analysis for digital portals.

    Run a subcommand (`analyze` or `tui`), or pass URLs directly for the
    default `analyze` behaviour::

        portallens "http://example.com/login?..."

    See `portallens analyze --help` and `portallens tui --help` for the
    per-subcommand options.
    """

    if ctx.invoked_subcommand is None:
        # `portallens` with no args at all — show help.
        click.echo(ctx.get_help())


@main.command(name="analyze")
@click.argument("urls", nargs=-1, required=True)
@_PORTAL_TYPE_OPTION
@_FETCH_OPTION
@_FOLLOW_REDIRECTS_OPTION
@_RESOLVE_DNS_OPTION
@_AUTH_OPTION
@_NOTES_OPTION
@click.option(
    "--output",
    "-o",
    "output",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write the report to this path instead of stdout.",
)
def analyze(
    urls: tuple[str, ...],
    portal_type: str,
    fetch_urls: bool,
    follow_redirects: bool,
    resolve_dns: bool,
    authorization_confirmed: bool,
    output: str | None,
    notes: str | None,
) -> None:
    """Analyze one or more portal URLs and emit a Markdown report."""

    report = _run_analysis(
        urls=urls,
        portal_type=portal_type,
        fetch_urls=fetch_urls,
        follow_redirects=follow_redirects,
        resolve_dns=resolve_dns,
        authorization_confirmed=authorization_confirmed,
        notes=notes,
    )
    markdown = render_markdown(report)

    if output is not None:
        from pathlib import Path

        Path(output).write_text(markdown, encoding="utf-8")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(markdown)


@main.command(name="tui")
@click.argument("urls", nargs=-1, required=True)
@_PORTAL_TYPE_OPTION
@_FETCH_OPTION
@_FOLLOW_REDIRECTS_OPTION
@_RESOLVE_DNS_OPTION
@_AUTH_OPTION
@_NOTES_OPTION
def tui(
    urls: tuple[str, ...],
    portal_type: str,
    fetch_urls: bool,
    follow_redirects: bool,
    resolve_dns: bool,
    authorization_confirmed: bool,
    notes: str | None,
) -> None:
    """Analyze portal URLs, then open the investigation-console TUI.

    Requires the `tui` extra: `pip install -e ".[tui]"`.
    """

    report = _run_analysis(
        urls=urls,
        portal_type=portal_type,
        fetch_urls=fetch_urls,
        follow_redirects=follow_redirects,
        resolve_dns=resolve_dns,
        authorization_confirmed=authorization_confirmed,
        notes=notes,
    )

    # Lazy import — keeps textual out of the core library's import graph
    # (ADR-7). A user who never runs `tui` never pays textual's import
    # cost or its dependency closure (rich, markdown-it-py, ...).
    try:
        from portallens.tui import PortalLensApp
    except ImportError as exc:
        click.echo(
            "The TUI requires the 'tui' extra. Install it with:\n"
            "    pip install -e \".[tui]\"\n"
            f"(underlying import error: {exc})",
            err=True,
        )
        sys.exit(2)

    app = PortalLensApp(report)
    # run() blocks until the user quits. run_async() would await; the
    # CLI is synchronous so run() is correct here.
    app.run()


if __name__ == "__main__":
    main()
