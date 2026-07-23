"""Console-safe output — the single boundary where text leaves for a terminal.

Some Windows consoles use a legacy code page (cp1252, cp437) that cannot
encode every character, and Python raises ``UnicodeEncodeError`` the moment it
tries to write one. PortalLens emits a redirect arrow (``->``), and — more to
the point — it emits **user-supplied data**: the URLs and query-parameter
values a user pastes become evidence and get printed in the report. Those can
carry arbitrary Unicode (an IDN hostname like ``café.wifi``, a percent-decoded
parameter).

Because the offending characters can come from user input, this *cannot* be
fixed by sanitizing source strings — that would be an endless, always-incomplete
game. It is handled here, once, at the boundary: encode-test against the target
stream's encoding and degrade only what that encoding can't represent. Output to
a UTF-8 terminal or a file keeps its full Unicode; a cp1252 console gets a
readable ASCII fallback instead of a crash.
"""

from __future__ import annotations

import sys

import click

# Readable ASCII stand-ins, tried before the lossy catch-all so a reader sees
# "->" rather than "?". Only consulted on the degrade path (a console that
# already can't encode the text), so UTF-8 terminals never see these.
_TRANSLITERATIONS = {
    "→": "->",   # → rightwards arrow — relationship direction
    "—": "-",    # — em dash
    "–": "-",    # – en dash
    "·": "|",    # · middle dot
    "…": "...",  # … ellipsis
    "≥": ">=",   # ≥
    "≤": "<=",   # ≤
}


def console_safe(text: str, encoding: str) -> str:
    """Return ``text`` unchanged if ``encoding`` can encode it, else degrade it.

    The fast path is a no-op — a UTF-8 stream (or a file) gets the text as-is.
    Only when the target encoding can't represent some character do we
    transliterate the known glyphs and replace anything still unencodable, so
    the call can never itself raise.
    """

    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        target = encoding
    except LookupError:
        # The stream reported an encoding Python doesn't know — we can't target
        # it, so fall back to plain ASCII, which every terminal can render.
        target = "ascii"

    for glyph, ascii_form in _TRANSLITERATIONS.items():
        text = text.replace(glyph, ascii_form)
    # Catch-all for anything the target code page still can't take
    # (e.g. a user-supplied IDN character with no ASCII stand-in).
    return text.encode(target, "replace").decode(target, "replace")


def echo(text: str, *, err: bool = False) -> None:
    """``click.echo``, but made safe for the target stream's encoding first.

    Route every report/CLI line a user might have influenced through this,
    rather than pre-sanitizing the strings that produce it.
    """

    stream = sys.stderr if err else sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    click.echo(console_safe(text, encoding), err=err)
