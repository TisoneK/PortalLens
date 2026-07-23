"""Confidence scoring — the spine of every PortalLens inference.

PortalLens never claims something as fact unless the evidence supports it.
Every inference carries an integer confidence in ``[0, 100]`` plus a
human-readable label, and the rubric for each label is documented below so
reports can justify the score rather than ask the reader to trust it.

Label rubric
------------
- **very_low** (0–19): speculative — no direct evidence; could easily be wrong.
- **low** (20–39): weak signal — one indirect indicator; treat as a hypothesis.
- **medium** (40–59): plausible — multiple indirect indicators or one strong one.
- **high** (60–79): likely — strong, specific evidence; alternative explanations exist but are less probable.
- **very_high** (80–100): established — direct, unambiguous evidence; contradicting it would itself need evidence.

The :func:`score` helper combines multiple independent evidence weights using
a noisy-OR-style rule so two independent medium signals can lift an inference
into the ``high`` band, but a single speculative signal never escapes
``low`` on its own.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum


class ConfidenceLabel(str, Enum):
    """Human-readable confidence band."""

    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"

    def __str__(self) -> str:
        return self.value


class Confidence:
    """An integer score in ``[0, 100]`` plus its derived label.

    Construct with an explicit integer or via :func:`score` to combine
    multiple evidence weights. ``Confidence(75)`` is the common form for
    a single-evidence inference.
    """

    __slots__ = ("value",)

    def __init__(self, value: int) -> None:
        if not 0 <= value <= 100:
            raise ValueError(f"confidence must be in [0, 100], got {value}")
        self.value = value

    @property
    def label(self) -> ConfidenceLabel:
        return _label_for(self.value)

    def __int__(self) -> int:
        return self.value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Confidence):
            return self.value == other.value
        if isinstance(other, int):
            return self.value == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)

    def __repr__(self) -> str:
        return f"Confidence({self.value}={self.label.value})"

    def __format__(self, spec: str) -> str:
        if not spec:
            return f"{self.value}% ({self.label.value})"
        return format(self.value, spec)


def _label_for(value: int) -> ConfidenceLabel:
    if value < 20:
        return ConfidenceLabel.VERY_LOW
    if value < 40:
        return ConfidenceLabel.LOW
    if value < 60:
        return ConfidenceLabel.MEDIUM
    if value < 80:
        return ConfidenceLabel.HIGH
    return ConfidenceLabel.VERY_HIGH


def score(weights: Iterable[int]) -> Confidence:
    """Combine independent evidence weights into one confidence.

    Uses a noisy-OR-style combination so independent signals reinforce
    each other but never reach 100% without overwhelming evidence:

        combined = 1 - prod(1 - w_i / 100)

    Each weight should itself be in ``[0, 100]``. Weights ≤ 0 are dropped
    (they carry no signal). An empty iterable yields ``Confidence(0)``.

    Examples
    --------
    >>> score([60])
    Confidence(60=high)
    >>> score([40, 40])  # two medium signals → high
    Confidence(64=high)
    >>> score([10, 10, 10])  # three weak signals stay low
    Confidence(27=low)
    """
    complement = 1.0
    saw_any = False
    for w in weights:
        if w <= 0:
            continue
        if not 0 <= w <= 100:
            raise ValueError(f"weight must be in [0, 100], got {w}")
        complement *= 1.0 - (w / 100.0)
        saw_any = True
    if not saw_any:
        return Confidence(0)
    combined = (1.0 - complement) * 100.0
    return Confidence(round(combined))
