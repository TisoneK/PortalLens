"""Confidence and severity styling for the TUI.

ADR-7 consequence: "Severity and status are **never encoded by colour
alone** — needed for accessibility and for monochrome terminals (Termux
included)."

Every function in this module returns a Textual markup string (or a
tuple of ``(text_label, style)``) where the **text label is always
present**. Colour is an optional enhancement layered on top, never the
sole carrier of meaning. A monochrome terminal sees ``low · 35%``; a
colour terminal sees the same string with a yellow tint. The
information is identical either way.

This module imports only from :mod:`portallens.confidence` (which has no
textual dependency), so it is safe to import at module load. The textual
markup strings it produces are plain strings until a Textual widget
renders them.
"""

from __future__ import annotations

from portallens.confidence import Confidence, _label_for

# Confidence band → Textual style. The label text (very_low / low / ...)
# is ALWAYS rendered alongside the percentage; colour is additive only.
# Styles chosen to degrade gracefully on monochrome terminals: they use
# Textual's named styles, which fall back to dim/bold rather than
# disappearing entirely when colour is unavailable.
_CONFIDENCE_STYLE: dict[str, str] = {
    "very_low": "dim",
    "low": "yellow",
    "medium": "cyan",
    "high": "green",
    "very_high": "bold green",
}


def confidence_markup(value: int) -> str:
    """Return Textual markup for a confidence value, e.g. ``[low · 35%]``.

    The label and percentage are always present in the text; colour wraps
    the whole badge but never replaces the words. On a monochrome
    terminal the reader sees ``[low · 35%]``; on a colour terminal they
    see the same string tinted yellow. The information is identical.

    The literal square brackets around the badge are escaped
    (``\\[``) so Textual's markup parser doesn't treat them as style
    tags. ``Text.from_markup`` unescapes them to literal ``[`` / ``]``
    on render.
    """

    label = _label_for(value)
    style = _CONFIDENCE_STYLE[label.value]
    return f"[{style}]\\[{label.value} · {value}%][/{style}]"


def auth_badge(authorized: bool) -> str:
    """Textual markup for the authorization badge: ``AUTH: authorized``.

    The label text is always present; colour is additive only (ADR-7 —
    never colour alone). A monochrome terminal reads the same words.
    """

    if authorized:
        return "[bold green]AUTH: authorized[/bold green]"
    return "[bold yellow]AUTH: passive[/bold yellow]"


def mode_badge(mode: str) -> str:
    """Textual markup for the console-mode badge: ``MODE: console``.

    Modes are ``console`` (on-demand), ``auto`` (auto-run next steps),
    and ``monitor`` (continuous probing). Text is the carrier; colour is
    additive.
    """

    styles = {"console": "bold", "auto": "bold cyan", "monitor": "bold magenta"}
    style = styles.get(mode, "bold")
    return f"[{style}]MODE: {mode}[/{style}]"


def confidence_label_text(value: int) -> str:
    """The plain-text label+percentage, no markup: ``low · 35%``.

    Use this where Textual markup is not wanted (e.g. a widget's
    ``name``, or a log line). Guaranteed to carry the label even if the
    consumer strips all markup.
    """

    label = _label_for(value)
    return f"{label.value} · {value}%"


def confidence_from_value(value: int) -> Confidence:
    """Wrap an integer into a :class:`Confidence` (re-exported convenience)."""

    return Confidence(value)


# Observation-kind → human heading + style. Again, the heading text is
# the carrier of meaning; colour is additive.
_OBSERVATION_KIND_HEADING: dict[str, tuple[str, str]] = {
    "fact": ("Observed Facts", "bold"),
    "inference": ("Inferences", "bold cyan"),
    "hypothesis": ("Hypotheses (require verification)", "bold yellow"),
}


def observation_heading(kind: str) -> tuple[str, str]:
    """Return ``(heading_text, style)`` for an observation kind.

    The heading text is always present; the style is additive. If the
    kind is unrecognized, a neutral heading is returned so the screen
    never goes blank.
    """

    return _OBSERVATION_KIND_HEADING.get(kind, (kind.title(), "bold"))


# Relationship-kind → human label. Relationship kinds are rendered as
# text (never colour-only) because they are the structural content of
# the relationship graph.
_RELATIONSHIP_KIND_LABEL: dict[str, str] = {
    "redirects_to": "redirects to",
    "uses_platform": "uses platform",
    "operates_network": "operates network",
    "resells_bandwidth": "resells bandwidth",
    "upstream_of": "upstream of",
    "authenticates_for": "authenticates for",
    "same_operator": "same operator as",
}


def relationship_kind_label(kind: str) -> str:
    """Human-readable label for a relationship kind, e.g. ``redirects to``."""

    return _RELATIONSHIP_KIND_LABEL.get(kind, kind.replace("_", " "))


# Width threshold for the relationship-graph layout swap. Below this,
# the tree and its detail pane stack vertically; at or above, they sit
# side by side. 100 is chosen so that a Termux portrait terminal (~40
# cols) and a typical phone landscape (~80 cols) both get the stacked
# form, while a desktop terminal (>=120 cols) gets the side-by-side form.
# This is the single width threshold in the TUI — ADR-7's "panels reflow
# and stack rather than assuming width" is implemented here.
WIDE_THRESHOLD = 100
