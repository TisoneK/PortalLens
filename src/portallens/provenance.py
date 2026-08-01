"""Provenance — how well-established a piece of analysis knowledge is.

Shared by the signature registry (ADR-5/6) and the security-check registry
(ADR-11): a rule transcribed from vendor documentation is not as trustworthy
as one checked against a real captured sample, and a calibrated report must
not present them identically. The enum lives in core (not in the captive_wifi
plugin) because the security checks are cross-cutting — they must be able to
record provenance without importing a plugin module.
"""

from __future__ import annotations

from enum import Enum


class Provenance(str, Enum):
    """How well-established a rule is.

    ``VALIDATED`` means a real captured sample matching this rule lives in
    this repo's test fixtures. ``DOCUMENTED`` means the rule was transcribed
    from vendor documentation and has not been checked against a captured
    sample — it can still fire, but the report says so.
    """

    VALIDATED = "validated against a captured URL in this repo's fixtures"
    DOCUMENTED = "transcribed from vendor documentation — not yet validated against a captured URL"
