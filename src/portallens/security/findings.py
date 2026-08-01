"""Security finding model — the disclosure record ADR-11 mandates.

Every finding carries the disclosure schema from the user's preferences:
Title, Affected asset, Evidence, Impact, Confidence, Recommended
remediation, and Verification status. The model lives in ``portal.py``
(:class:`~portallens.portal.SecurityFinding`) so ``PortalReport`` can carry
findings without importing this package; this module re-exports it plus the
``Severity`` enum for convenience.
"""

from __future__ import annotations

from portallens.portal import SecurityFinding, Severity

__all__ = ["SecurityFinding", "Severity"]
