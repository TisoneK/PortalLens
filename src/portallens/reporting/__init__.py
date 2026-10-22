"""Reporting — render a :class:`PortalReport` for human consumption.

Today only Markdown is implemented. The Markdown renderer is the
canonical output: it's what the CLI prints, what the test suite
snapshots, and what a responsible-disclosure email would paste. Future
renderers (HTML, JSON, SARIF for security findings) plug in alongside
this one without changing the report model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from portallens.confidence import ConfidenceLabel, _label_for
from portallens.portal import PortalReport, PortalType, SecurityFinding
from portallens.reporting.sarif import render_sarif

if TYPE_CHECKING:
    from portallens.wifi.watch import AccessWatchReport

__all__ = ["render_markdown", "render_sarif", "render_watch_markdown"]

_TYPE_LABELS: dict[PortalType, str] = {
    PortalType.CAPTIVE_WIFI: "Captive Wi-Fi Portal",
    PortalType.WEB_AUTH: "Web Authentication Portal",
    PortalType.PAYMENT: "Payment Portal",
    PortalType.ISP: "ISP Portal",
}


def render_markdown(report: PortalReport, *, title: str | None = None) -> str:
    """Render ``report`` as a Markdown document.

    The output is structured so a reader can scan top-to-bottom and
    always know whether they're reading an observed fact, an inference,
    or a hypothesis — and what evidence supports each.
    """

    portal_label = _TYPE_LABELS.get(report.portal_type, report.portal_type.value)
    heading = title or f"PortalLens Report - {portal_label}"

    lines: list[str] = []
    lines.append(f"# {heading}")
    lines.append("")
    lines.append(f"**Primary URL:** `{report.primary_url}`")
    lines.append(f"**Portal type:** {portal_label}")
    lines.append("")

    # Executive summary — headline confidence on the strongest fingerprint
    lines.append("## Executive Summary")
    lines.append("")
    fp = report.strongest_fingerprint()
    if fp is not None:
        fp_label = _label_for(fp.confidence)
        lines.append(
            f"- Strongest platform fingerprint: **{fp.platform}** "
            f"({fp.confidence}% / {fp_label.value})"
        )
    else:
        lines.append("- No platform fingerprint could be derived from the supplied inputs.")
    inferred_relationships = [r for r in report.relationships if r.confidence >= 40]
    if inferred_relationships:
        lines.append(f"- Inferred relationships (>=40% confidence): {len(inferred_relationships)}")
    else:
        lines.append("- No relationships met the 40% confidence threshold for inclusion in the summary.")
    if report.open_questions:
        lines.append(f"- Open questions: {len(report.open_questions)} - see the Open Questions section.")
    lines.append("")

    # Evidence — raw inputs
    lines.append("## Captured Evidence")
    lines.append("")
    if not report.evidence:
        lines.append("_No evidence was captured. Passive analysis produced no observations._")
        lines.append("")
    else:
        lines.append("| ID | Type | Source | Key | Value (redacted) |")
        lines.append("|---|---|---|---|---|")
        for ev in report.evidence:
            value = _redact(ev.value)
            lines.append(
                f"| {ev.id} | {ev.type.value} | `{ev.source}` | `{ev.key}` | `{value}` |"
            )
        lines.append("")

    # Observations — facts / inferences / hypotheses, grouped
    for kind, obs_label in [
        ("fact", "Observed Facts"),
        ("inference", "Inferences"),
        ("hypothesis", "Hypotheses (require verification)"),
    ]:
        rows = report.observations_of_kind(kind)
        if not rows:
            continue
        lines.append(f"## {obs_label}")
        lines.append("")
        for obs in rows:
            ev_ids = ", ".join(obs.evidence_ids) if obs.evidence_ids else "-"
            conf_label = _label_for(obs.confidence)
            lines.append(f"- **[{conf_label.value} | {obs.confidence}%]** {obs.statement}")
            lines.append(f"  - Evidence: {ev_ids}")
            if obs.note:
                lines.append(f"  - Note: {obs.note}")
        lines.append("")

    # Fingerprints
    if report.fingerprints:
        lines.append("## Platform Fingerprints")
        lines.append("")
        lines.append("| Platform | Version | Confidence | Evidence |")
        lines.append("|---|---|---|---|")
        for fp in sorted(report.fingerprints, key=lambda f: -f.confidence):
            label = _label_for(fp.confidence)
            ev_ids = ", ".join(fp.evidence_ids) if fp.evidence_ids else "-"
            lines.append(
                f"| {fp.platform} | {fp.version or '-'} | "
                f"{fp.confidence}% ({label.value}) | {ev_ids} |"
            )
        lines.append("")

    # Relationships
    if report.relationships:
        lines.append("## Inferred Relationships")
        lines.append("")
        lines.append("| Relationship | Other entity | Confidence | Evidence |")
        lines.append("|---|---|---|---|")
        for rel in sorted(report.relationships, key=lambda r: -r.confidence):
            label = _label_for(rel.confidence)
            ev_ids = ", ".join(rel.evidence_ids) if rel.evidence_ids else "-"
            lines.append(
                f"| {rel.kind.value} | `{rel.other}` | "
                f"{rel.confidence}% ({label.value}) | {ev_ids} |"
            )
        lines.append("")

    # Security findings — the disclosure records (ADR-11). ADR-17 made the
    # prose fields optional: the renderer emits whatever the finding carries
    # and skips what it doesn't.
    if report.findings:
        lines.append("## Security Findings")
        lines.append("")
        lines.append(
            "_Findings may be lightweight: check, title, severity, and "
            "confidence are required; Impact, Remediation, Verification "
            "status, and evidence citations are included when present._"
        )
        lines.append("")
        for f in sorted(report.findings, key=lambda f: -f.confidence):
            label = _label_for(f.confidence)
            lines.append(
                f"- **[{f.severity.value} | {f.confidence}% ({label.value})] "
                f"{f.title}**"
            )
            lines.append(f"  - Check: `{f.check_slug}`")
            if f.affected:
                lines.append(f"  - Affected asset: `{f.affected}`")
            if f.evidence_ids:
                lines.append(f"  - Evidence: {', '.join(f.evidence_ids)}")
            if f.impact:
                lines.append(f"  - Impact: {f.impact}")
            if f.uncertainty:
                lines.append(f"  - Uncertainty: {f.uncertainty}")
            if f.remediation:
                lines.append(f"  - Recommended remediation: {f.remediation}")
            if f.verification_status:
                lines.append(f"  - Verification status: {f.verification_status}")
        lines.append("")

    # Open questions
    if report.open_questions:
        lines.append("## Open Questions")
        lines.append("")
        lines.append(
            "_These are gaps the analyzer could not close with the supplied "
            "evidence. Resolving them would require either additional input "
            "(HTML/HAR captures, DNS records) or an explicitly authorized "
            "active assessment._"
        )
        lines.append("")
        for q in report.open_questions:
            lines.append(f"- {q.question}")
            if q.resolves_with:
                lines.append(f"  - Resolves with: {', '.join(q.resolves_with)}")
        lines.append("")

    # Footer — confidence rubric
    lines.append("## Confidence Rubric")
    lines.append("")
    lines.append(
        "Every non-fact statement carries an integer score in `[0, 100]` "
        "and a derived label. Reports distinguish observed facts (direct "
        "evidence), inferences (conclusions drawn from evidence), and "
        "hypotheses (speculative explanations requiring verification - "
        "confidence capped at `low` by convention)."
    )
    lines.append("")
    lines.append("| Range | Label | Meaning |")
    lines.append("|---|---|---|")
    for rng, lbl, meaning in [
        ("0-19", ConfidenceLabel.VERY_LOW, "Speculative - no direct evidence; could easily be wrong."),
        ("20-39", ConfidenceLabel.LOW, "Weak signal - one indirect indicator; treat as a hypothesis."),
        ("40-59", ConfidenceLabel.MEDIUM, "Plausible - multiple indirect indicators or one strong one."),
        ("60-79", ConfidenceLabel.HIGH, "Likely - strong, specific evidence; alternatives less probable."),
        ("80-100", ConfidenceLabel.VERY_HIGH, "Established - direct, unambiguous evidence."),
    ]:
        lines.append(f"| {rng} | {lbl.value} | {meaning} |")
    lines.append("")

    return "\n".join(lines)


_NO_PLAN_SLUG = "gateway_session_without_plan"
_PAYMENT_CODE_SLUG = "session_username_payment_code_shape"
#: Findings whose evidence comes from the authorized gateway session view —
#: these carry a source-trust label (gateway itself vs third-party billing host).
_SESSION_VIEW_SLUGS = (_NO_PLAN_SLUG, _PAYMENT_CODE_SLUG)


def render_watch_markdown(
    report: AccessWatchReport,
    *,
    title: str | None = None,
    verbose: bool = False,
) -> str:
    """Render a connectivity-watch report as Markdown.

    The default is a condensed digest: the verdict first, the findings
    with their evidence collapsed to what differs, and only the latest
    session view. The raw record stays in the journal; a report says what
    the run established. ``verbose=True`` renders the full history —
    every observation, every evidence row, all tables. Both modes are
    documents of record: they describe the operator in the third person,
    never address the reader.
    """

    if verbose:
        return _render_watch_markdown_verbose(report, title=title)
    return _render_watch_markdown_condensed(report, title=title)


def _render_watch_markdown_verbose(
    report: AccessWatchReport,
    *,
    title: str | None = None,
) -> str:
    """The full report: every observation, transition, and evidence row."""

    heading = title or "PortalLens Watch Report"
    sampled_states = {sample.state.value for sample in report.samples}

    lines: list[str] = [f"# {heading}", ""]
    lines.append(f"**Watched target:** {report.target or '(not labelled)'}")
    lines.append(f"**Observations:** {len(report.samples)} across {len({s.epoch for s in report.samples})} connection epoch(s)")
    lines.append(f"**Recorded boundaries:** {len(report.boundaries)}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    if report.findings:
        lines.append(f"- Findings raised: {len(report.findings)}")
    else:
        lines.append("- Findings raised: none")
    if report.samples:
        lines.append(f"- Observed classifications: {', '.join(sorted(sampled_states))}")
    else:
        lines.append("- No observations recorded yet.")
    post_expiry = [e for e in report.evidence if e.key == "watch:post-expiry-access"]
    if post_expiry:
        lines.append(
            f"- Verified unrestricted samples after a recorded expiry with no "
            f"recorded renewal: {len(post_expiry)}"
        )
    mismatches = [e for e in report.evidence if e.key == "watch:portal-claim-mismatch"]
    if mismatches:
        lines.append(
            f"- Samples where access worked but the portal showed no package: {len(mismatches)}"
        )
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    if report.findings:
        for finding in report.findings:
            status = f" - {finding.verification_status}" if finding.verification_status else ""
            lines.append(
                f"- **[{finding.severity.value} | {finding.confidence}%] {finding.title}**{status}"
            )
            lines.append(f"  - Check: `{finding.check_slug}`")
            if finding.impact:
                lines.append(f"  - Impact: {finding.impact}")
            if finding.uncertainty:
                lines.append(f"  - Uncertainty: {finding.uncertainty}")
            if finding.remediation:
                lines.append(f"  - Remediation: {finding.remediation}")
            if finding.evidence_ids:
                lines.append(f"  - Evidence: {', '.join(finding.evidence_ids)}")
    else:
        lines.append("No check fired on the recorded history.")
    lines.append("")

    lines.append("## Recorded boundaries")
    lines.append("")
    if report.boundaries:
        lines.append("| Kind | At | Note |")
        lines.append("|---|---|---|")
        for boundary in report.boundaries:
            lines.append(
                f"| {boundary.kind.value} | {boundary.at.isoformat()} | {boundary.note or ''} |"
            )
    else:
        lines.append("None recorded - no expiry is known, so post-expiry access cannot be judged.")
    lines.append("")

    lines.append("## Observations")
    lines.append("")
    if report.samples:
        lines.append(
            "| # | Epoch | Observed at | Classification | Portal claim | Profile | Portal |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for index, sample in enumerate(report.samples, start=1):
            portal = f"`{_redact(sample.portal_url)}`" if sample.portal_url else "-"
            claim = sample.portal_claim.value.replace("_", " ") if sample.portal_claim else "not recorded"
            lines.append(
                f"| {index} | {sample.epoch} | {sample.observed_at.isoformat()} | "
                f"{sample.state.value} | {claim} | {sample.profile_name} | {portal} |"
            )
    else:
        lines.append("No observations recorded yet.")
    lines.append("")

    changes = [t for t in report.transitions if t.from_state is not None]
    lines.append("## Transitions")
    lines.append("")
    if changes:
        for transition in changes:
            assert transition.from_state is not None
            where = "after a reconnect" if transition.new_epoch else "within one connection"
            lines.append(
                f"- {transition.from_state.value} -> {transition.to_state.value} "
                f"({where}) at {transition.observed_at.isoformat()}"
            )
    else:
        lines.append("No classification changes recorded.")
    lines.append("")

    lines.append("## Supporting evidence")
    lines.append("")
    derived = [e for e in report.evidence if e.key.startswith("watch:")]
    if derived:
        lines.append("| ID | Observed at | Key | Value | Note |")
        lines.append("|---|---|---|---|---|")
        for evidence in derived:
            note = (evidence.note or "").replace("|", "\\|")
            observed = evidence.observed_at.isoformat() if evidence.observed_at else "-"
            lines.append(
                f"| {evidence.id} | {observed} | `{evidence.key}` | "
                f"`{_redact(evidence.value)}` | {note} |"
            )
    else:
        lines.append("No watch-derived evidence yet.")
    lines.append("")

    annotated = [s for s in report.samples if s.note]
    lines.append("## Observation notes")
    lines.append("")
    if annotated:
        for sample in annotated:
            lines.append(f"- {sample.observed_at.isoformat()}: {sample.note}")
    else:
        lines.append("No free-text notes recorded.")
    lines.append("")

    snapshots = [s.snapshot for s in report.samples if s.snapshot is not None]
    lines.append("## Local network (latest sample)")
    lines.append("")
    if snapshots:
        latest = snapshots[-1]
        lines.append("| Fact | Value |")
        lines.append("|---|---|")
        lines.append(f"| SSID | {latest.ssid or '(unknown)'} |")
        lines.append(f"| Interface | {latest.interface or '(unknown)'} |")
        lines.append(f"| Client IPv4 | {latest.client_ipv4 or '(unknown)'} |")
        vendor = f" ({latest.gateway_vendor})" if latest.gateway_vendor else ""
        mac = latest.gateway_mac or "(unknown)"
        lines.append(f"| Gateway | {latest.gateway_ipv4 or '(unknown)'} {mac}{vendor} |")
        obtained = latest.dhcp_lease_obtained.isoformat() if latest.dhcp_lease_obtained else "(unknown)"
        expires = latest.dhcp_lease_expires.isoformat() if latest.dhcp_lease_expires else "(unknown)"
        lines.append(f"| DHCP lease | obtained {obtained} - expires {expires} |")
        dns = ", ".join(latest.dns_servers) if latest.dns_servers else "(unknown)"
        lines.append(f"| DNS servers | {dns} |")
    else:
        lines.append("No local network snapshot recorded (host facts unavailable).")
    lines.append("")

    sessions = [s for s in report.samples if s.gateway_session is not None]
    lines.append("## Gateway session view (authorized status fetch)")
    lines.append("")
    if sessions:
        for sample in sessions:
            session = sample.gateway_session
            assert session is not None
            lines.append(f"- Observed at {sample.observed_at.isoformat()}:")
            lines.append(f"  - Username: `{session.username or '(none)'}`")
            lines.append(f"  - Device: {session.mac or '(unknown)'} / {session.ip or '(unknown)'}")
            lines.append(f"  - Plan: {session.plan or '(empty)'}")
            limits = (
                f"session-left {session.session_left or '?'}, "
                f"expires-on {session.expires_on or '?'}, "
                f"bytes-left {session.bytes_left or '?'}"
            )
            lines.append(f"  - Limits: {limits}")
            lines.append(f"  - Source: {session.source_url or '(unknown)'}")
            if session.unread_view:
                pairs = ", ".join(
                    f"{pair.label!r}" + (f" = {pair.value!r}" if pair.value else "")
                    for pair in session.view.unmapped[:6]
                )
                lines.append(
                    f"  - **The page rendered {session.view.pairs_read} label/value "
                    "pair(s) but none named a session user this build recognises"
                    + (f" ({pairs})" if pairs else "")
                    + ". The session view was found and not read — a parser gap, "
                    "not an absent session.**"
                )
            if sample.gateway_fetch_perturbed is True:
                lines.append(
                    "  - **The classification changed across this fetch — the "
                    "fetch may have perturbed the hotspot session.**"
                )
    else:
        lines.append(
            "No gateway status fetch recorded. A run with `--gateway-status "
            "--authorized` captures the gateway's own session view."
        )
    lines.append("")

    lines.append("## How to read this report")
    lines.append("")
    lines.append(
        "- The portal claim is what the portal showed the operator when they "
        "looked; the tool does not fetch the portal while measuring, because "
        "that request can itself reset the hotspot session."
    )
    for note in report.notes:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def _render_watch_markdown_condensed(
    report: AccessWatchReport,
    *,
    title: str | None = None,
) -> str:
    """The digest: verdict first, findings collapsed to what differs.

    Repeated evidence rows are grouped with the observations where they
    were seen; the session view shows only the latest fetch; table
    columns that would be constant or empty for this run are omitted.
    """

    heading = title or "PortalLens Watch Report"
    lines: list[str] = [f"# {heading}", ""]
    lines.append(f"**Watched target:** {report.target or '(not labelled)'}")
    if report.samples:
        first, last = report.samples[0], report.samples[-1]
        epochs = len({s.epoch for s in report.samples})
        lines.append(
            f"**Observations:** {len(report.samples)} between "
            f"{first.observed_at.isoformat()} and {last.observed_at.isoformat()}, "
            f"across {epochs} connection epoch(s)"
        )
    else:
        lines.append("**Observations:** none")
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    if not report.samples:
        lines.append("- No observations recorded yet.")
    elif not report.boundaries:
        lines.append(
            "- Expiry: not judged — no boundary recorded. Record the package "
            "expiry with `--expiry` to test post-expiry access."
        )
    else:
        post_expiry = [e for e in report.evidence if e.key == "watch:post-expiry-access"]
        if post_expiry:
            lines.append(
                f"- Post-expiry access: observed — {len(post_expiry)} verified "
                "unrestricted sample(s) after the recorded expiry, no renewal recorded."
            )
        else:
            lines.append(
                "- Post-expiry access: not observed — no verified unrestricted "
                "sample after the recorded expiry."
            )
    lines.append(
        f"- Findings raised: {len(report.findings)}" if report.findings
        else "- Findings raised: none"
    )
    lines.append("")

    lines.append("## What changed")
    lines.append("")
    lines.extend(_classification_change_lines(report))
    lines.extend(_session_view_change_lines(report))
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    if not report.findings:
        lines.append("No check fired on the recorded history.")
    else:
        payment = next(
            (f for f in report.findings if f.check_slug == _PAYMENT_CODE_SLUG), None
        )
        no_plan = next(
            (f for f in report.findings if f.check_slug == _NO_PLAN_SLUG), None
        )
        for finding in report.findings:
            if finding.check_slug == _PAYMENT_CODE_SLUG:
                continue  # nested under the no-plan finding, or rendered below
            lines.extend(_condensed_finding_lines(report, finding))
            if payment is not None and finding.check_slug == _NO_PLAN_SLUG:
                # The payment-code hit is attribution for the no-plan session
                # (whose payment created it), not an independent issue.
                lines.append(
                    f"  - Attribution: `{payment.check_slug}` — "
                    f"[{payment.severity.value} | {payment.confidence}%] "
                    f"{payment.title}; a format inference about who the "
                    "username is, not a second issue."
                )
        if payment is not None and no_plan is None:
            lines.extend(_condensed_finding_lines(report, payment))
    lines.append("")

    sessions = [s for s in report.samples if s.gateway_session is not None]
    lines.append("## Gateway session view (latest fetch)")
    lines.append("")
    if sessions:
        sample = sessions[-1]
        session = sample.gateway_session
        assert session is not None
        lines.append(f"- Observed at {sample.observed_at.isoformat()}:")
        lines.append(f"  - Username: `{session.username or '(none)'}`")
        lines.append(f"  - Device: {session.mac or '(unknown)'} / {session.ip or '(unknown)'}")
        lines.append(f"  - Plan: {session.plan or '(empty)'}")
        lines.append(
            f"  - Limits: session-left {session.session_left or '?'}, "
            f"expires-on {session.expires_on or '?'}, bytes-left {session.bytes_left or '?'}"
        )
        lines.append(f"  - Source: {session.source_url or '(unknown)'}")
        if sample.gateway_fetch_perturbed is True:
            lines.append(
                "  - **The classification changed across this fetch — the "
                "fetch may have perturbed the hotspot session.**"
            )
    else:
        lines.append(
            "No gateway status fetch recorded. A run with `--gateway-status "
            "--authorized` captures the gateway's own session view."
        )
    lines.append("")

    snapshots = [s.snapshot for s in report.samples if s.snapshot is not None]
    lines.append("## Local network (latest sample)")
    lines.append("")
    if snapshots:
        latest = snapshots[-1]
        lines.append("| Fact | Value |")
        lines.append("|---|---|")
        lines.append(f"| SSID | {latest.ssid or '(unknown)'} |")
        lines.append(f"| Interface | {latest.interface or '(unknown)'} |")
        lines.append(f"| Client IPv4 | {latest.client_ipv4 or '(unknown)'} |")
        vendor = f" ({latest.gateway_vendor})" if latest.gateway_vendor else ""
        mac = latest.gateway_mac or "(unknown)"
        lines.append(f"| Gateway | {latest.gateway_ipv4 or '(unknown)'} {mac}{vendor} |")
        obtained = latest.dhcp_lease_obtained.isoformat() if latest.dhcp_lease_obtained else "(unknown)"
        expires = latest.dhcp_lease_expires.isoformat() if latest.dhcp_lease_expires else "(unknown)"
        lines.append(f"| DHCP lease | obtained {obtained} - expires {expires} |")
        dns = ", ".join(latest.dns_servers) if latest.dns_servers else "(unknown)"
        lines.append(f"| DNS servers | {dns} |")
    else:
        lines.append("No local network snapshot recorded (host facts unavailable).")
    lines.append("")

    annotated = [s for s in report.samples if s.note]
    if annotated:
        lines.append("## Observation notes")
        lines.append("")
        for sample in annotated:
            lines.append(f"- {sample.observed_at.isoformat()}: {sample.note}")
        lines.append("")

    derived = [e for e in report.evidence if e.key.startswith("watch:")]
    lines.append("## Supporting evidence (grouped)")
    lines.append("")
    if derived:
        for (key, value, note), observations in _grouped_evidence(report).items():
            where = (
                f" — observation(s) {', '.join(str(n) for n in observations)}"
                if observations
                else ""
            )
            note_suffix = f" {note}" if note else ""
            lines.append(f"- `{key}` = `{_redact(value)}`{where}.{note_suffix}")
    else:
        lines.append("No watch-derived evidence yet.")
    lines.append("")

    reading_notes: list[str] = []
    if any(s.portal_claim is not None for s in report.samples):
        reading_notes.append(
            "The portal claim is what the portal showed the operator when "
            "they looked; the tool does not fetch the portal while measuring, "
            "because that request can itself reset the hotspot session."
        )
    reading_notes.extend(report.notes)
    if reading_notes:
        lines.append("## How to read this report")
        lines.append("")
        for note in reading_notes:
            lines.append(f"- {note}")
        lines.append("")
    return "\n".join(lines)


def _classification_change_lines(report: AccessWatchReport) -> list[str]:
    """One line summarising classification: counts, then real transitions."""

    if not report.samples:
        return ["- Classification: no observations."]
    counts: dict[str, int] = {}
    for sample in report.samples:
        counts[sample.state.value] = counts.get(sample.state.value, 0) + 1
    tally = ", ".join(f"{state} x{counts[state]}" for state in sorted(counts))
    changes = [t for t in report.transitions if t.from_state is not None]
    lines = [f"- Classification: {tally}, no changes." if not changes else f"- Classification: {tally}."]
    for transition in changes:
        assert transition.from_state is not None
        where = "after a reconnect" if transition.new_epoch else "within one connection"
        lines.append(
            f"  - {transition.from_state.value} -> {transition.to_state.value} "
            f"({where}) at {transition.observed_at.isoformat()}"
        )
    return lines


def _session_view_change_lines(report: AccessWatchReport) -> list[str]:
    """Session-view presence per observation run, with the source of each part.

    Classification transitions live in the samples; whether the gateway
    showed a session at all is a separate dimension the report used to
    leave invisible (a fetch that finds no view looks identical to one
    that was never run, without this).
    """

    segments: list[tuple[int, int, str, str | None]] = []
    start: int | None = None
    prev_label: str | None = None
    prev_source: str | None = None
    for index, sample in enumerate(report.samples, start=1):
        session = sample.gateway_session
        if session is None:
            label, source = "no fetch", None
        elif session.active:
            label, source = "active session", session.source_url
        elif session.unread_view:
            label, source = "session view unread", session.source_url
        else:
            label, source = "no session view", session.source_url
        if label != prev_label:
            if prev_label is not None and start is not None:
                segments.append((start, index - 1, prev_label, prev_source))
            start, prev_label, prev_source = index, label, source
    if prev_label is not None and start is not None:
        segments.append((start, len(report.samples), prev_label, prev_source))

    if not segments:
        return ["- Session view: no gateway status fetch recorded."]
    parts = []
    for begin, end, label, source in segments:
        span = f"observation {begin}" if begin == end else f"observations {begin}-{end}"
        source_label = _source_label(report, source) if source else None
        suffix = f" (source: {source_label})" if source_label else ""
        parts.append(f"{label} at {span}{suffix}")
    return [f"- Session view: {'; '.join(parts)}."]


def _condensed_finding_lines(
    report: AccessWatchReport, finding: SecurityFinding
) -> list[str]:
    """One finding as a compact block: observed fact, source, read, caveats."""

    status = f" ({finding.verification_status})" if finding.verification_status else ""
    lines = [
        f"- **[{finding.severity.value} | {finding.confidence}%] {finding.title}**{status}"
    ]
    observed = _finding_observed_note(report, finding)
    if observed:
        lines.append(f"  - Observed: {observed}")
    lines.append(f"  - Check: `{finding.check_slug}`")
    if finding.check_slug in _SESSION_VIEW_SLUGS:
        source = _finding_source_label(report, finding)
        if source:
            lines.append(f"  - Source: {source}")
    if finding.impact:
        lines.append(f"  - Impact: {finding.impact}")
    if finding.uncertainty:
        lines.append(f"  - Uncertainty: {finding.uncertainty}")
    if finding.remediation:
        lines.append(f"  - Remediation: {finding.remediation}")
    if finding.evidence_ids:
        observations = _evidence_observations(report, finding.evidence_ids)
        where = (
            f" (observations {', '.join(str(n) for n in observations)})"
            if observations
            else ""
        )
        lines.append(f"  - Evidence: {', '.join(finding.evidence_ids)}{where}")
    return lines


def _observation_numbers(report: AccessWatchReport) -> dict[object, int]:
    """Map each sample's timestamp to its 1-based observation number."""

    return {sample.observed_at: index for index, sample in enumerate(report.samples, 1)}


def _grouped_evidence(
    report: AccessWatchReport,
) -> dict[tuple[str, str, str], list[int]]:
    """Identical evidence rows collapsed, with where each was seen.

    Consecutive fetches of the same session view produce identical
    evidence apart from timestamps; a digest names the observations.
    """

    numbers = _observation_numbers(report)
    grouped: dict[tuple[str, str, str], list[int]] = {}
    for evidence in report.evidence:
        if not evidence.key.startswith("watch:"):
            continue
        key = (evidence.key, evidence.value, evidence.note or "")
        number = numbers.get(evidence.observed_at)
        bucket = grouped.setdefault(key, [])
        if number is not None and number not in bucket:
            bucket.append(number)
    for bucket in grouped.values():
        bucket.sort()
    return grouped


def _finding_observed_note(
    report: AccessWatchReport, finding: SecurityFinding
) -> str | None:
    """The recorded observation behind a finding (its first evidence note)."""

    by_id = {e.id: e for e in report.evidence}
    for evidence_id in finding.evidence_ids:
        record = by_id.get(evidence_id)
        if record is not None and record.note:
            return record.note
    return None


def _evidence_observations(
    report: AccessWatchReport, evidence_ids: list[str]
) -> list[int]:
    numbers = _observation_numbers(report)
    wanted = set(evidence_ids)
    found = {
        numbers[e.observed_at]
        for e in report.evidence
        if e.id in wanted and e.observed_at in numbers
    }
    return sorted(found)


def _source_label(report: AccessWatchReport, source_url: str | None) -> str | None:
    """Where a session view came from — the gateway itself reads differently
    from a third-party billing host reached through the gateway's shell page."""

    if not source_url:
        return None
    host = urlsplit(source_url).hostname or source_url
    gateway = next(
        (
            s.snapshot.gateway_ipv4
            for s in reversed(report.samples)
            if s.snapshot is not None and s.snapshot.gateway_ipv4
        ),
        None,
    )
    if gateway is not None and host == gateway:
        return f"gateway {gateway} directly"
    return f"third-party host {host}, reached via the gateway's status shell"


def _finding_source_label(
    report: AccessWatchReport, finding: SecurityFinding
) -> str | None:
    """The source label for a session-view finding: its evidence comes from
    the session fetches, so label the latest fetched view's origin."""

    sessions = [s for s in report.samples if s.gateway_session is not None]
    if not sessions:
        return None
    latest = sessions[-1].gateway_session
    assert latest is not None
    return _source_label(report, latest.source_url)


def _redact(value: str, *, keep: int = 64) -> str:
    """Trim long values and replace clearly-sensitive patterns.

    We don't try to detect every secret — the rule is "if it looks like
    a token, cookie, or fingerprint blob, truncate aggressively." A
    4 KB canvas fingerprint is never useful in a report; a 64-char
    prefix is plenty to identify it.
    """

    if len(value) > keep:
        return value[:keep] + "..."
    return value
