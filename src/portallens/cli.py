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

from portallens.output import echo
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
    port_scan: bool,
    authorization_confirmed: bool,
    notes: str | None,
) -> PortalReport:
    """Run analysis and return the :class:`PortalReport`.

    Shared by both subcommands. Raises :class:`SystemExit` on
    authorization or plugin-lookup failure (after printing a message).
    """

    if not urls:
        echo("Error: at least one URL is required.", err=True)
        sys.exit(2)

    # Active-mode guard — require explicit authorization confirmation.
    active = any((fetch_urls, follow_redirects, resolve_dns, port_scan))
    if active and not authorization_confirmed:
        echo(
            "Active analysis (--fetch-urls / --follow-redirects / --resolve-dns / "
            "--port-scan) requires explicit authorization for every URL supplied.\n"
            "Re-run with --i-have-authorization if you have it.",
            err=True,
        )
        sys.exit(2)

    policy = AcquisitionPolicy(
        fetch_urls=fetch_urls,
        follow_redirects=follow_redirects,
        resolve_dns=resolve_dns,
        port_scan=port_scan,
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
        echo(str(exc), err=True)
        sys.exit(2)

    portal = portal_cls()
    report = portal.analyze(context)

    # NetAudit pass (ADR-12): when the policy enables active probing, run the
    # authorized active-assessment over the report's observed hosts and merge
    # the probe evidence + findings back into the report. OSINT (RIPEstat)
    # is NOT part of this pass — it runs as a `portallens step` against a
    # persisted investigation, per ADR-9/13.
    if port_scan:
        report = _run_netaudit(report, policy)
    return report


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
    help="Portal type to analyze as. Defaults to captive_wifi - the only implemented plugin today.",
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
_PORT_SCAN_OPTION = click.option(
    "--port-scan",
    is_flag=True,
    default=False,
    help="Enable active admin-port probing (NetAudit). Requires --i-have-authorization.",
)
_AUTH_OPTION = click.option(
    "--i-have-authorization",
    "authorization_confirmed",
    is_flag=True,
    default=False,
    help=(
        "Confirm you have authorization for active analysis of every URL supplied. "
        "Required when any active flag (--fetch-urls / --resolve-dns / --port-scan) is set. "
        "OSINT-only techniques (RIPEstat) run per-step via `portallens authorize + step`."
    ),
)
_NOTES_OPTION = click.option(
    "--notes",
    default=None,
    help="Free-text notes to attach to the analysis context (e.g. 'captured from Android Chrome').",
)
_DB_OPTION = click.option(
    "--db",
    "db_path",
    type=click.Path(dir_okay=False),
    default=None,
    help=(
        "Path to the investigations database. Defaults to $PORTALLENS_DB, else "
        "$XDG_DATA_HOME/portallens/investigations.db (see ADR-8)."
    ),
)
_FORMAT_OPTION = click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "sarif"], case_sensitive=False),
    default="markdown",
    show_default=True,
    help="Output format: Markdown (human) or SARIF 2.1.0 (machine).",
)


def _render(report: PortalReport, output_format: str) -> str:
    """Render ``report`` in the requested format."""

    if output_format.lower() == "sarif":
        from portallens.reporting import render_sarif

        return render_sarif(report)
    return render_markdown(report)


def _run_netaudit(report: PortalReport, policy: AcquisitionPolicy) -> PortalReport:
    """Run the authorized active-assessment pass and merge its results.

    Only runs when the policy enables an active technique NetAudit knows
    about (admin-port probing today). The probe evidence and any findings
    it produces are appended to the passive report.
    """

    from portallens.security.audit import run_netaudit
    from portallens.steps.registry import hosts_from_report

    hosts = hosts_from_report(report)
    if not hosts:
        return report
    result = run_netaudit(hosts, policy)
    if not result.evidence and not result.findings:
        return report

    from portallens.steps import refine_open_questions

    merged_evidence = [*report.evidence, *result.evidence]
    return report.model_copy(
        update={
            "evidence": merged_evidence,
            "findings": [*report.findings, *result.findings],
            # Probe evidence answers the admin-exposure open question — close
            # it so the report doesn't keep asking what the probe answered
            # (ADR-9 loop closure).
            "open_questions": refine_open_questions(report.open_questions, merged_evidence),
        }
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
        echo(ctx.get_help())


@main.command(name="analyze")
@click.argument("urls", nargs=-1, required=True)
@_PORTAL_TYPE_OPTION
@_FETCH_OPTION
@_FOLLOW_REDIRECTS_OPTION
@_RESOLVE_DNS_OPTION
@_PORT_SCAN_OPTION
@_AUTH_OPTION
@_NOTES_OPTION
@_FORMAT_OPTION
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
    port_scan: bool,
    authorization_confirmed: bool,
    output: str | None,
    output_format: str,
    notes: str | None,
) -> None:
    """Analyze one or more portal URLs and emit a report (Markdown or SARIF)."""

    report = _run_analysis(
        urls=urls,
        portal_type=portal_type,
        fetch_urls=fetch_urls,
        follow_redirects=follow_redirects,
        resolve_dns=resolve_dns,
        port_scan=port_scan,
        authorization_confirmed=authorization_confirmed,
        notes=notes,
    )
    rendered = _render(report, output_format)

    if output is not None:
        from pathlib import Path

        Path(output).write_text(rendered, encoding="utf-8")
        echo(f"Report written to {output}", err=True)
    else:
        echo(rendered)


@main.command(name="tui")
@click.argument("urls", nargs=-1, required=True)
@_PORTAL_TYPE_OPTION
@_FETCH_OPTION
@_FOLLOW_REDIRECTS_OPTION
@_RESOLVE_DNS_OPTION
@_PORT_SCAN_OPTION
@_AUTH_OPTION
@_NOTES_OPTION
def tui(
    urls: tuple[str, ...],
    portal_type: str,
    fetch_urls: bool,
    follow_redirects: bool,
    resolve_dns: bool,
    port_scan: bool,
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
        port_scan=port_scan,
        authorization_confirmed=authorization_confirmed,
        notes=notes,
    )

    # Lazy import — keeps textual out of the core library's import graph
    # (ADR-7). A user who never runs `tui` never pays textual's import
    # cost or its dependency closure (rich, markdown-it-py, ...).
    try:
        from portallens.tui import PortalLensApp
    except ImportError as exc:
        echo(
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


# ---------------------------------------------------------------------------
# Investigation persistence (ADR-8) — create, list, show, authorize.
# These operate on the SQLite store; `investigate` runs step-zero analysis
# and persists the result, the rest read/update stored investigations.
# ---------------------------------------------------------------------------


@main.command(name="investigate")
@click.argument("urls", nargs=-1, required=True)
@_PORTAL_TYPE_OPTION
@_FETCH_OPTION
@_FOLLOW_REDIRECTS_OPTION
@_RESOLVE_DNS_OPTION
@_PORT_SCAN_OPTION
@_AUTH_OPTION
@_NOTES_OPTION
@_DB_OPTION
def investigate(
    urls: tuple[str, ...],
    portal_type: str,
    fetch_urls: bool,
    follow_redirects: bool,
    resolve_dns: bool,
    port_scan: bool,
    authorization_confirmed: bool,
    notes: str | None,
    db_path: str | None,
) -> None:
    """Analyze portal URLs and save the result as a persisted investigation.

    Prints the new investigation's id. Inspect it later with
    `portallens show <id>` — the analysis outlives the process.
    """

    from portallens.investigation import Investigation, InvestigationStore

    report = _run_analysis(
        urls=urls,
        portal_type=portal_type,
        fetch_urls=fetch_urls,
        follow_redirects=follow_redirects,
        resolve_dns=resolve_dns,
        port_scan=port_scan,
        authorization_confirmed=authorization_confirmed,
        notes=notes,
    )
    investigation = Investigation.start(
        report,
        portal_type=PortalType(portal_type.lower()),
        user_notes=notes,
    )
    with InvestigationStore(db_path) as store:
        store.save(investigation)

    fp = report.strongest_fingerprint()
    headline = f"{fp.platform} ({fp.confidence}%)" if fp else "no platform fingerprint"
    echo(f"Investigation saved: {investigation.id}")
    echo(f"  Target:   {investigation.target}")
    echo(f"  Strongest fingerprint: {headline}")
    echo(f"  Relationships: {len(report.relationships)} | Open questions: {len(report.open_questions)}")
    echo(f"\nInspect it:  portallens show {investigation.id}")


@main.command(name="investigations")
@_DB_OPTION
def investigations(db_path: str | None) -> None:
    """List saved investigations, newest first."""

    from portallens.investigation import InvestigationStore

    with InvestigationStore(db_path) as store:
        summaries = store.list()

    if not summaries:
        echo("No investigations saved yet. Create one with `portallens investigate <url>`.")
        return

    for s in summaries:
        echo(f"{s.id}")
        echo(f"    target:  {s.target}")
        echo(f"    type:    {s.portal_type.value}    updated: {s.updated_at.isoformat(timespec='seconds')}")


@main.command(name="show")
@click.argument("investigation_id")
@click.option("--audit", is_flag=True, default=False, help="Show the audit log and authorizations instead of the report.")
@_FORMAT_OPTION
@_DB_OPTION
def show(investigation_id: str, audit: bool, output_format: str, db_path: str | None) -> None:
    """Render a saved investigation's report (or, with --audit, its trail)."""

    from portallens.investigation import InvestigationStore

    with InvestigationStore(db_path) as store:
        investigation = store.get(investigation_id)

    if investigation is None:
        echo(f"No investigation with id {investigation_id!r}.", err=True)
        sys.exit(1)

    if not audit:
        echo(_render(investigation.report, output_format))
        return

    echo(f"# Audit trail - {investigation.id}")
    echo(f"\nTarget: {investigation.target}")
    echo(f"Created: {investigation.created_at.isoformat(timespec='seconds')}")
    granted = ", ".join(sorted(investigation.authorized_techniques)) or "none"
    echo(f"Authorized techniques: {granted}")
    echo("\n## Log")
    for entry in investigation.audit_log:
        echo(f"  [{entry.at.isoformat(timespec='seconds')}] {entry.kind}: {entry.detail}")


@main.command(name="authorize")
@click.argument("investigation_id")
@click.option(
    "--technique",
    required=True,
    help="The active technique you assert authorization for (e.g. fetch_urls, resolve_dns).",
)
@click.option("--note", default=None, help="Optional note recorded with the authorization.")
@_DB_OPTION
def authorize(investigation_id: str, technique: str, note: str | None, db_path: str | None) -> None:
    """Record, per ADR-10, that you assert authorization for one active technique.

    The assertion is timestamped and appended to the investigation's audit
    trail. It does not itself run anything — it is the recorded authorization
    a later active step checks against.
    """

    from portallens.investigation import InvestigationStore

    with InvestigationStore(db_path) as store:
        investigation = store.get(investigation_id)
        if investigation is None:
            echo(f"No investigation with id {investigation_id!r}.", err=True)
            sys.exit(1)
        try:
            grant = investigation.authorize(technique, note=note)
        except ValueError as exc:
            echo(f"Error: {exc}", err=True)
            sys.exit(2)
        store.save(investigation)

    echo(
        f"Authorization recorded for {grant.technique!r} on {investigation.id} "
        f"at {grant.granted_at.isoformat(timespec='seconds')}."
    )


@main.command(name="step")
@click.argument("investigation_id")
@click.argument("step_slug")
@_DB_OPTION
def step(investigation_id: str, step_slug: str, db_path: str | None) -> None:
    """Run one registered analysis step against a saved investigation (ADR-9).

    Loads the investigation, checks the step's authorization requirement
    (ADR-10), runs the step, appends its evidence to the persisted
    investigation, and saves. This is the "pull the thread" loop:

        portallens authorize <id> --technique resolve_dns
        portallens step <id> resolve_dns
        portallens step <id> ip_asn_lookup
    """

    from portallens.investigation import InvestigationStore
    from portallens.steps import compute_next_steps, step_for_slug

    with InvestigationStore(db_path) as store:
        investigation = store.get(investigation_id)
        if investigation is None:
            echo(f"No investigation with id {investigation_id!r}.", err=True)
            sys.exit(1)

        step_ = step_for_slug(step_slug)
        if step_ is None:
            available = ", ".join(s.slug for s in compute_next_steps(investigation.report.open_questions)) or "none"
            echo(
                f"Unknown analysis step {step_slug!r}. Steps this investigation's "
                f"open questions name: {available}",
                err=True,
            )
            sys.exit(2)

        if step_.requires and not investigation.is_authorized(step_.requires):
            echo(
                f"Step {step_slug!r} requires authorization for {step_.requires!r}, "
                f"which is not recorded for {investigation.id}.\n"
                f"Record it first: portallens authorize {investigation.id} "
                f"--technique {step_.requires}",
                err=True,
            )
            sys.exit(2)

        # Run with exactly the techniques the operator has recorded
        # authorization for (ADR-10 scope is a set, never implied — ADR-13).
        # `_policy_for_technique` would enable only the step's `requires`,
        # which would strand ip_asn_lookup on hostname targets: it needs
        # resolve_dns too, and only an explicit resolve_dns authorization
        # may enable it.
        policy = _policy_for_authorizations(investigation.authorized_techniques)
        evidence = step_.run(investigation, policy)
        if evidence:
            investigation.append_evidence(evidence, step=step_.slug)
        else:
            # A step that found nothing is itself audit-worthy (ADR-10):
            # "resolve_dns ran, returned no records" is defensibility evidence.
            investigation.record("step", f"Analysis step {step_slug!r} ran and produced no evidence.")
        # New evidence may fire checks the passive pass didn't see, and may
        # answer open questions — recompute both so the persisted report is
        # current (ADR-9 loop closure). The report is the immutable snapshot;
        # rebuild it rather than mutating in place.
        from portallens.security.checks import run_checks
        from portallens.steps import refine_open_questions

        investigation.report = investigation.report.model_copy(
            update={
                "findings": run_checks(investigation.report.evidence),
                "open_questions": refine_open_questions(
                    investigation.report.open_questions, investigation.report.evidence
                ),
            }
        )
        store.save(investigation)

        echo(f"Step {step_slug!r} produced {len(evidence)} evidence record(s).")
        for ev in evidence:
            echo(f"  [{ev.type.value}] {ev.key}: {ev.value}")
        # ADR-13 transparency: if the step skipped hostnames for lack of DNS
        # consent, say so — "produced 0" must never be a silent no-op.
        if step_.slug == "ip_asn_lookup":
            from portallens.steps.ip_asn import dnsless_hostnames

            skipped = dnsless_hostnames(investigation, policy)
            if skipped:
                echo(
                    f"  (hostnames skipped - OSINT consent never implies DNS "
                    f"consent; authorize resolve_dns to resolve then look up: "
                    f"portallens authorize {investigation.id} --technique resolve_dns. "
                    f"Skipped: {', '.join(skipped)})"
                )
        echo(f"Investigation {investigation.id} updated (audit log appended).")


def _policy_for_authorizations(authorized: set[str]) -> AcquisitionPolicy:
    """Build the policy a step runs under, from recorded authorizations.

    The `step` verb enables exactly the techniques the operator has recorded
    authorization for (ADR-10: scope is a set). A step may need more than its
    own ``requires`` slug — ``ip_asn_lookup`` needs ``resolve_dns`` to resolve
    hostname targets before the ASN lookup — and only an explicit, recorded
    resolve_dns authorization may enable it (ADR-13: no flag implies another).
    """

    return AcquisitionPolicy(
        fetch_urls="fetch_urls" in authorized,
        follow_redirects="follow_redirects" in authorized,
        resolve_dns="resolve_dns" in authorized,
        probe_tls="probe_tls" in authorized,
        port_scan="port_scan" in authorized,
        use_osint_apis="use_osint_apis" in authorized,
    )


if __name__ == "__main__":
    main()
