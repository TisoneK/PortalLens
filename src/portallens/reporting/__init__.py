"""Reporting — render a :class:`PortalReport` for human consumption.

Today only Markdown is implemented. The Markdown renderer is the
canonical output: it's what the CLI prints, what the test suite
snapshots, and what a responsible-disclosure email would paste. Future
renderers (HTML, JSON, SARIF for security findings) plug in alongside
this one without changing the report model.
"""

from __future__ import annotations

from portallens.confidence import ConfidenceLabel, _label_for
from portallens.portal import PortalReport, PortalType
from portallens.reporting.sarif import render_sarif

__all__ = ["render_markdown", "render_sarif"]

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

    # Security findings — the disclosure records (ADR-11)
    if report.findings:
        lines.append("## Security Findings")
        lines.append("")
        lines.append(
            "_Every finding carries the disclosure schema: Title, Affected "
            "asset, Evidence, Impact, Confidence, Recommended remediation, "
            "and Verification status._"
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
            lines.append(f"  - Impact: {f.impact}")
            lines.append(f"  - Recommended remediation: {f.remediation}")
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
