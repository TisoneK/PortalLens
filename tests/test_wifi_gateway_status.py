"""Tests for the MikroTik hotspot gateway status parser and fetch.

Fixtures reproduce both shapes observed live on KITENGELA@10: the
RouterOS-style label/value table (STATUS_HTML, two ``<td>`` cells per
row, empty PLAN and START-TIME cells, "Not assigned *" limit rows); the
billing-provider template the gateway's shell page iframes
(BILLING_HTML, ``<th>`` labels, ``<td>`` values, TITLE/VALUE thead); and
the shell page itself (SHELL_HTML), which carries no table at all. The
flattened fixture is the user's copy-paste rendering of the session
view, which must parse identically.
"""

from __future__ import annotations

from collections.abc import Callable

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

# The live KITENGELA@10 gateway serves /status as a shell whose iframe
# carries the real session view on the billing provider's endpoint —
# labels rendered as <th> cells, values as <td>, and a TITLE/VALUE thead.
SHELL_HTML = """\
<html><head><title>Internet Hotspot - Status</title></head>
<body><iframe src="https://asp.billnasi.com/endpoints/status?username=UIBMX5SUY3" \
frameborder="0" width="100%"></iframe></body></html>
"""

BILLING_HTML = """\
<!DOCTYPE html><html lang="en"><head><title>CHECK VOUCHER STATUS VERBOSE</title></head>
<body><div class="container-fluid my-3">
<table style=' border-collapse: collapse;'>
<thead>
<th>TITLE</th>
<th>VALUE</th>
</thead>
<tr>
    <th>USERNAME</th>
    <td>UIBMX5SUY3</td>
</tr>
<tr>
    <th>MAC</th>
    <td>98:AF:65:7C:6A:69</td>
</tr>
<tr>
    <th>IP</th>
    <td>11.220.2.109</td>
</tr>
<tr>
    <th>PLAN</th>
    <td></td>
</tr>
<tr>
    <th>START-TIME</th>
    <td>                            </td>
</tr>
<tr>
    <th>SESSION-LEFT</th>
    <td>Not assigned *</td>
</tr>
<tr>
    <th>EXPIRES-ON</th>
    <td>Not assigned *</td>
</tr>
<tr>
    <th>BYTES LEFT</th>
    <td>Not assigned *</td>
</tr>
</table>
</body></html>
"""


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


class TestBillingTemplate:
    def test_th_label_cells_parse_like_td(self) -> None:
        info = parse_mikrotik_status(
            BILLING_HTML, source_url="https://asp.billnasi.com/endpoints/status"
        )
        assert info.username == "UIBMX5SUY3"
        assert info.mac == "98:AF:65:7C:6A:69"
        assert info.ip == "11.220.2.109"
        assert info.plan is None
        assert info.start_time is None  # whitespace-only cell
        assert info.session_left == "Not assigned *"
        assert info.expires_on == "Not assigned *"
        assert info.bytes_left == "Not assigned *"
        assert info.active
        assert info.limits_unassigned

    def test_shell_page_alone_is_not_a_session(self) -> None:
        info = parse_mikrotik_status(SHELL_HTML)
        assert not info.active


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

    def _queued_fetch(
        self, documents: list[FetchedDocument]
    ) -> tuple[list[str], Callable[[str, AcquisitionPolicy], FetchedDocument]]:
        queue = list(documents)
        seen: list[str] = []

        def fake_fetch(url: str, policy: AcquisitionPolicy) -> FetchedDocument:
            seen.append(url)
            return queue.pop(0)

        return seen, fake_fetch

    def test_shell_page_is_followed_one_level_to_the_session_view(self) -> None:
        billing_url = "https://asp.billnasi.com/endpoints/status?username=UIBMX5SUY3"
        seen, fake_fetch = self._queued_fetch(
            [
                FetchedDocument(
                    final_url="http://11.220.0.1/status",
                    status_code=200,
                    headers={},
                    body=SHELL_HTML,
                ),
                FetchedDocument(
                    final_url=billing_url,
                    status_code=200,
                    headers={},
                    body=BILLING_HTML,
                ),
            ]
        )
        policy = AcquisitionPolicy(authorized=True)
        info = fetch_gateway_session("http://11.220.0.1/status", policy, fetch=fake_fetch)
        assert seen == ["http://11.220.0.1/status", billing_url]
        assert info.username == "UIBMX5SUY3"
        assert info.plan is None
        assert info.limits_unassigned
        assert info.source_url == billing_url

    def test_iframe_fetch_failure_degrades_to_url_username(self) -> None:
        billing_url = "https://asp.billnasi.com/endpoints/status?username=UIBMX5SUY3"
        seen: list[str] = []

        def fake_fetch(url: str, policy: AcquisitionPolicy) -> FetchedDocument:
            seen.append(url)
            if url == "http://11.220.0.1/status":
                return FetchedDocument(
                    final_url=url, status_code=200, headers={}, body=SHELL_HTML
                )
            raise ConnectionError("billing endpoint unreachable")

        policy = AcquisitionPolicy(authorized=True)
        info = fetch_gateway_session("http://11.220.0.1/status", policy, fetch=fake_fetch)
        assert seen == ["http://11.220.0.1/status", billing_url]
        assert info.username == "UIBMX5SUY3"
        assert info.mac is None
        assert not info.limits_unassigned
        assert info.source_url == billing_url

    def test_iframe_without_username_param_returns_empty_session(self) -> None:
        seen, fake_fetch = self._queued_fetch(
            [
                FetchedDocument(
                    final_url="http://11.220.0.1/status",
                    status_code=200,
                    headers={},
                    body=SHELL_HTML.replace("?username=UIBMX5SUY3", ""),
                ),
                FetchedDocument(
                    final_url="https://asp.billnasi.com/endpoints/status",
                    status_code=200,
                    headers={},
                    body="<html><body>no session</body></html>",
                ),
            ]
        )
        policy = AcquisitionPolicy(authorized=True)
        info = fetch_gateway_session("http://11.220.0.1/status", policy, fetch=fake_fetch)
        assert len(seen) == 2
        assert not info.active

    def test_non_http_iframe_is_not_followed(self) -> None:
        seen: list[str] = []

        def fake_fetch(url: str, policy: AcquisitionPolicy) -> FetchedDocument:
            seen.append(url)
            return FetchedDocument(
                final_url=url,
                status_code=200,
                headers={},
                body=SHELL_HTML.replace(
                    "https://asp.billnasi.com/endpoints/status?username=UIBMX5SUY3",
                    "javascript:void(0)",
                ),
            )

        policy = AcquisitionPolicy(authorized=True)
        info = fetch_gateway_session("http://11.220.0.1/status", policy, fetch=fake_fetch)
        assert seen == ["http://11.220.0.1/status"]
        assert not info.active

    def test_iframe_follow_stops_at_one_level(self) -> None:
        billing_url = "https://asp.billnasi.com/endpoints/status?username=UIBMX5SUY3"
        nested = BILLING_HTML.replace(
            "<table style=' border-collapse: collapse;'>",
            "<iframe src=\"https://asp.billnasi.com/endpoints/other\"></iframe>"
            "<table style=' border-collapse: collapse;'>",
        )
        seen, fake_fetch = self._queued_fetch(
            [
                FetchedDocument(
                    final_url="http://11.220.0.1/status",
                    status_code=200,
                    headers={},
                    body=SHELL_HTML,
                ),
                FetchedDocument(
                    final_url=billing_url, status_code=200, headers={}, body=nested
                ),
            ]
        )
        policy = AcquisitionPolicy(authorized=True)
        info = fetch_gateway_session("http://11.220.0.1/status", policy, fetch=fake_fetch)
        assert len(seen) == 2  # the nested iframe inside the view is not followed
        assert info.username == "UIBMX5SUY3"
