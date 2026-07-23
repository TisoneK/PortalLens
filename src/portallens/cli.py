"""PortalLens CLI — analyze a portal URL and print a Markdown report.

Examples
--------
Passive analysis (default — no network access):

    portallens "http://maz.wifi/login?dst=..."

Passive analysis with multiple URLs (the local captive hostname AND the
external portal URL the user was redirected to):

    portallens \\
        "http://maz.wifi/login?dst=..." \\
        "https://captive.ispman.tech/hotspots/.../select?..."

Active analysis — requires explicit authorization for the target:

    portallens --fetch-urls --i-have-authorization "https://example.com/login"
"""

from __future__ import annotations

import sys

import click

from portallens.plugins.captive_wifi import CaptiveWifiPortal  # noqa: F401 — registers the plugin
from portallens.portal import AcquisitionPolicy, AnalysisContext, PortalType
from portallens.registry import get_portal_class
from portallens.reporting import render_markdown


@click.command(
    name="portallens",
    help="Analyze a portal URL and print an evidence-backed Markdown report.",
)
@click.argument("urls", nargs=-1, required=True)
@click.option(
    "--type",
    "portal_type",
    type=click.Choice([t.value for t in PortalType], case_sensitive=False),
    default=PortalType.CAPTIVE_WIFI.value,
    show_default=True,
    help="Portal type to analyze as. Defaults to captive_wifi — the only implemented plugin today.",
)
@click.option(
    "--fetch-urls",
    is_flag=True,
    default=False,
    help="Enable active HTTP fetching. Requires --i-have-authorization.",
)
@click.option(
    "--follow-redirects",
    is_flag=True,
    default=False,
    help="Follow HTTP redirects when --fetch-urls is set. Off by default.",
)
@click.option(
    "--resolve-dns",
    is_flag=True,
    default=False,
    help="Enable active DNS resolution. Requires --i-have-authorization.",
)
@click.option(
    "--i-have-authorization",
    "authorization_confirmed",
    is_flag=True,
    default=False,
    help=(
        "Confirm you have authorization for active analysis of every URL supplied. "
        "Required when --fetch-urls or --resolve-dns is set."
    ),
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write the report to this path instead of stdout.",
)
@click.option(
    "--notes",
    default=None,
    help="Free-text notes to attach to the analysis context (e.g. 'captured from Android Chrome').",
)
def main(
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
    report = portal.analyze(context)
    markdown = render_markdown(report)

    if output is not None:
        from pathlib import Path

        Path(output).write_text(markdown, encoding="utf-8")
        click.echo(f"Report written to {output}", err=True)
    else:
        click.echo(markdown)


if __name__ == "__main__":
    main()
