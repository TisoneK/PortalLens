"""Tests for the MikroTik hotspot gateway status parser and fetch.

The HTML fixture reproduces the shape of the RouterOS hotspot status
template observed live on KITENGELA@10 (label/value rows, empty PLAN and
START-TIME cells, "Not assigned *" limit rows); the flattened fixture is the
user's copy-paste rendering of the same page, which must parse identically.
"""

from __future__ import annotations

from portallens.acquisition.fetcher import FetchedDocument
from portallens.portal import AcquisitionPolicy
from portallens.wifi.gateway_status import (
    fetch_gateway_session,
    matches_payment_code_shape,
    parse_mikrotik_status,
    status_url_for_gateway,
)

STATUS_HTML = """\
<html><head><title>hotspot &gt; status</title></head><body>
<h1>Status</h1>
<table>
<tr><td align="right">USERNAME</td><td>UIBMX5SUY3</td></tr>
<tr><td align="right">MAC</td><td>98:af:65:7c:6a:69</td></tr>
<tr><td align="right">IP</td><td>11.220.2.109</td></tr>
<tr><td align="right">PLAN</td><td></td></tr>
<tr><td align="right">START-TIME</td><td></td></tr>
<tr><td align="right">SESSION-LEFT</td><td>Not assigned *</td></tr>
<tr><td align="right">EXPIRES-ON</td><td>Not assigned *</td></tr>
<tr><td align="right">BYTES LEFT</td><td>Not assigned *</td></tr>
</table>
<p>* limits apply only with a plan</p>
</body></html>
"""

STATUS_TEXT = (
    "TITLE VALUE USERNAME UIBMX5SUY3 MAC 98:AF:65:7C:6A:69 IP 11.220.2.109 "
    "PLAN START-TIME SESSION-LEFT Not assigned * EXPIRES-ON Not assigned * "
    "BYTES LEFT Not assigned *"
)


class TestParseStatusPage:
    def test_html_form_parses_all_fields(self) -> None:
        info = parse_mikrotik_status(STATUS_HTML, source_url="http://11.220.0.1/status")
        assert info.username == "UIBMX5SUY3"
        assert info.mac == "98:AF:65:7C:6A:69"
        assert info.ip == "11.220.2.109"
        assert info.plan is None
        assert info.start_time is None
        assert info.session_left == "Not assigned *"
        assert info.expires_on == "Not assigned *"
        assert info.bytes_left == "Not assigned *"
        assert info.source_url == "http://11.220.0.1/status"

    def test_flattened_paste_parses_identically(self) -> None:
        info = parse_mikrotik_status(STATUS_TEXT)
        assert info.username == "UIBMX5SUY3"
        assert info.plan is None
        assert info.limits_unassigned

    def test_active_requires_a_username(self) -> None:
        assert parse_mikrotik_status(STATUS_HTML).active
        assert not parse_mikrotik_status("<html><body>no session here</body></html>").active

    def test_limits_unassigned_requires_all_three_cells(self) -> None:
        limited = STATUS_HTML.replace("Not assigned *", "2h13m30s", 1)
        info = parse_mikrotik_status(limited)
        assert not info.limits_unassigned

    def test_profiled_session_keeps_plan(self) -> None:
        html = STATUS_HTML.replace("<tr><td align=\"right\">PLAN</td><td></td></tr>",
                                   "<tr><td align=\"right\">PLAN</td><td>1 Day</td></tr>")
        html = html.replace("Not assigned *", "23h59m").replace(
            "<tr><td align=\"right\">START-TIME</td><td></td></tr>",
            "<tr><td align=\"right\">START-TIME</td><td>2026-10-21 08:00:00</td></tr>",
        )
        info = parse_mikrotik_status(html)
        assert info.plan == "1 Day"
        assert info.start_time == "2026-10-21 08:00:00"
        assert not info.limits_unassigned


class TestPaymentCodeShape:
    def test_mpesa_style_code_matches(self) -> None:
        assert matches_payment_code_shape("UIBMX5SUY3")
        assert matches_payment_code_shape("QGH7X9Y2Z3")

    def test_non_matching_shapes_do_not(self) -> None:
        assert not matches_payment_code_shape("trial-user")
        assert not matches_payment_code_shape("uibmx5suy3")  # lowercase
        assert not matches_payment_code_shape("SHORT9")
        assert not matches_payment_code_shape("ELEVEN12345")  # 11 chars
        assert not matches_payment_code_shape(None)


class TestFetch:
    def test_url_builder_targets_gateway_status_page(self) -> None:
        assert status_url_for_gateway("11.220.0.1") == "http://11.220.0.1/status"

    def test_fetch_uses_injected_transport(self) -> None:
        seen: list[tuple[str, AcquisitionPolicy]] = []

        def fake_fetch(url: str, policy: AcquisitionPolicy) -> FetchedDocument:
            seen.append((url, policy))
            return FetchedDocument(
                final_url=url,
                status_code=200,
                headers={},
                body=STATUS_HTML,
            )

        policy = AcquisitionPolicy(authorized=True)
        info = fetch_gateway_session("http://11.220.0.1/status", policy, fetch=fake_fetch)
        assert seen == [("http://11.220.0.1/status", policy)]
        assert info.username == "UIBMX5SUY3"
