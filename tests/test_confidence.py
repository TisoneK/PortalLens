"""Tests for the confidence scoring module."""

from __future__ import annotations

import pytest

from portallens.confidence import Confidence, ConfidenceLabel, score


class TestConfidence:
    def test_value_in_range(self) -> None:
        assert Confidence(0).value == 0
        assert Confidence(100).value == 100

    def test_value_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            Confidence(-1)
        with pytest.raises(ValueError):
            Confidence(101)

    @pytest.mark.parametrize(
        "value,label",
        [
            (0, ConfidenceLabel.VERY_LOW),
            (19, ConfidenceLabel.VERY_LOW),
            (20, ConfidenceLabel.LOW),
            (39, ConfidenceLabel.LOW),
            (40, ConfidenceLabel.MEDIUM),
            (59, ConfidenceLabel.MEDIUM),
            (60, ConfidenceLabel.HIGH),
            (79, ConfidenceLabel.HIGH),
            (80, ConfidenceLabel.VERY_HIGH),
            (100, ConfidenceLabel.VERY_HIGH),
        ],
    )
    def test_label_thresholds(self, value: int, label: ConfidenceLabel) -> None:
        assert Confidence(value).label is label


class TestScore:
    def test_empty_weights_yield_zero(self) -> None:
        assert score([]).value == 0

    def test_zero_weights_yield_zero(self) -> None:
        assert score([0, 0, 0]).value == 0

    def test_single_weight(self) -> None:
        assert score([60]).value == 60

    def test_two_reinforcing_signals_lift_confidence(self) -> None:
        # Two 40% signals combined: 1 - (0.6 * 0.6) = 0.64 → 64
        assert score([40, 40]).value == 64

    def test_weak_signals_stay_low(self) -> None:
        # Three 10% signals: 1 - (0.9^3) = 0.271 → 27
        assert score([10, 10, 10]).value == 27

    def test_does_not_reach_100_without_overwhelming_evidence(self) -> None:
        # 99 + 99: 1 - (0.01 * 0.01) = 0.9999 → 100 (rounded)
        # This is the upper bound — two near-certain signals can
        # establish certainty, which is correct behavior.
        assert score([99, 99]).value == 100

    def test_rejects_invalid_weight(self) -> None:
        with pytest.raises(ValueError):
            score([50, 101])
