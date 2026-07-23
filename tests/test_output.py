"""Tests for the console-safety boundary (`portallens.output`).

The point of the boundary is to handle characters that source-string edits
can't reach — chiefly **user-supplied** Unicode in URLs and parameters. So the
tests assert both the mechanism (encode-test + degrade) and that a report built
from a Unicode URL survives emission to a cp1252 console.
"""

from __future__ import annotations

from portallens.evidence import reset_evidence_ids
from portallens.output import console_safe
from portallens.plugins.captive_wifi import CaptiveWifiPortal
from portallens.portal import AnalysisContext
from portallens.reporting import render_markdown


class TestConsoleSafe:
    def test_utf8_is_a_no_op(self) -> None:
        # A capable stream keeps the text exactly — arrows and all.
        text = "maz.wifi → captive.ispman.tech · café"
        assert console_safe(text, "utf-8") == text

    def test_arrow_degrades_under_cp1252(self) -> None:
        # The arrow (U+2192) is the character that actually can't encode to
        # cp1252 — it gets a readable ASCII stand-in, not a "?".
        assert console_safe("a → b", "cp1252") == "a -> b"

    def test_middle_dot_is_fine_under_cp1252(self) -> None:
        # The subtlety behind the earlier whack-a-mole: · (U+00B7) *is* in
        # cp1252, so it takes the no-op fast path there — it was never the
        # cp1252 breaker. The arrow was.
        assert console_safe("x · y", "cp1252") == "x · y"

    def test_known_glyphs_get_readable_standins_when_encoding_cant_take_them(self) -> None:
        # Under an encoding that genuinely can't represent them (ASCII), the
        # stand-ins fire: · -> |, — -> -.
        assert console_safe("x · y — z", "ascii") == "x | y - z"

    def test_result_is_always_encodable(self) -> None:
        # A cp1252 console truly can't take an arrow; whatever we return must
        # encode without raising.
        out = console_safe("a → b", "cp1252")
        out.encode("cp1252")  # must not raise

    def test_user_supplied_idn_does_not_crash(self) -> None:
        # café.wifi has no ASCII stand-in for 'é'; the catch-all replaces it
        # rather than raising. This is the case no source edit could fix.
        out = console_safe("host: café.wifi → portal", "cp1252")
        out.encode("cp1252")  # must not raise
        assert "->" in out  # the arrow still degraded cleanly

    def test_unknown_encoding_name_does_not_raise(self) -> None:
        # A bogus stream encoding must degrade, not explode.
        out = console_safe("a → b", "not-a-real-codec")
        assert isinstance(out, str)


class TestReportSurvivesLegacyConsole:
    def test_full_report_from_unicode_url_encodes_to_cp1252(self) -> None:
        # The real gap: a user pastes a URL with a non-cp1252 character. It
        # becomes evidence and reaches the report. Emitting it must not crash
        # a Windows console — which source-string sanitizing could never
        # guarantee, because the character came from input.
        reset_evidence_ids()
        unicode_url = "http://café.wifi/login?dst=http%3A%2F%2Fexample.com&note=naïve"
        report = CaptiveWifiPortal().analyze(AnalysisContext(urls=[unicode_url]))
        markdown = render_markdown(report)
        # As the CLI's echo() would: degrade to the console encoding, then encode.
        console_safe(markdown, "cp1252").encode("cp1252")  # must not raise
