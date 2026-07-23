"""Active acquisition — HTTP fetching.

Only used when the caller passes ``AcquisitionPolicy(fetch_urls=True)``
AND has authorization for the target. Passive analysis never imports
this module, so a typo can't accidentally turn a passive scan into an
active one.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from portallens.acquisition import assert_policy
from portallens.portal import AcquisitionPolicy


@dataclass(frozen=True)
class FetchedDocument:
    """The result of an authorized HTTP fetch.

    Carries the final URL (after redirects, if allowed), the status
    code, the response headers, and the body. The body is capped at
    ``max_body_bytes`` (default 1 MiB) — PortalLens is an analyzer, not
    a crawler.
    """

    final_url: str
    status_code: int
    headers: dict[str, str]
    body: str


def fetch(
    url: str,
    policy: AcquisitionPolicy,
    *,
    max_body_bytes: int = 1_048_576,
    timeout_seconds: float = 10.0,
    user_agent: str = "PortalLens/0.1 (+https://github.com/TisoneK/PortalLens)",
) -> FetchedDocument:
    """Fetch ``url`` with the given :class:`AcquisitionPolicy`.

    Raises :class:`AcquisitionDenied` if ``policy.fetch_urls`` is False.
    The fetch follows redirects only if ``policy.follow_redirects`` is
    True — otherwise a 3xx response is returned as-is.

    The caller is responsible for having authorization to fetch ``url``.
    PortalLens does not — and cannot — verify that for you.
    """

    assert_policy(policy, "fetch_urls")
    headers = {"User-Agent": user_agent}
    with httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=policy.follow_redirects,
        max_redirects=10,
    ) as client:
        response = client.get(url, headers=headers)
        body = response.text[:max_body_bytes]
        return FetchedDocument(
            final_url=str(response.url),
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items()},
            body=body,
        )
