"""Unit tests for the arithmetic of Sections 3-5, independent of real data."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from civicalign.alignment import alignment, rank_all
from civicalign.space import MAX_DISTANCE, nth_from_left


def test_even_count_median_averages_the_two_middles():
    """A 100-member chamber has no single middle member: the median must be the
    mean of the 50th and 51st, not the 50th alone."""
    from civicalign.space import median
    assert median([0.0, 0.2, 0.4, 0.6]) == pytest.approx(0.3)


def test_cloture_pivot_is_the_60th_from_the_left():
    vals = [i / 100 for i in range(100)]  # 0.00 .. 0.99
    assert nth_from_left(vals, 60) == 0.59


def test_signed_gap_distinguishes_extreme_from_crossing_over():
    # same absolute gap, completely different situations
    extreme = alignment("A", "Extreme", "XX", senator_coord=0.7, state_coord=0.2)
    crossed = alignment("B", "Crossed", "YY", senator_coord=0.2, state_coord=-0.3)
    # NOTE: compare with approx. These are binary floats -- 0.7 - 0.2 is
    # 0.49999999999999994, so exact equality fails. Anywhere coordinates are
    # compared for equality (ranking ties, deduplicating medians) needs the
    # same care.
    assert extreme.abs_gap == pytest.approx(crossed.abs_gap)
    assert extreme.crosses_over is False
    assert crossed.crosses_over is True


def test_spec_score_compresses_as_documented():
    """A gap of 1.0 is enormous, yet the spec formula still calls it 50%."""
    a = alignment("A", "N", "XX", senator_coord=0.5, state_coord=-0.5)
    assert a.abs_gap == pytest.approx(1.0)
    assert a.spec_score == pytest.approx(50.0)


def test_rank_puts_worst_aligned_first():
    aligns = [
        alignment("A", "Small", "XX", 0.1, 0.0),
        alignment("B", "Big", "YY", 0.9, 0.0),
        alignment("C", "Mid", "ZZ", 0.5, 0.0),
    ]
    ranked = rank_all(aligns)
    assert [a.name for a in ranked] == ["Big", "Mid", "Small"]
    assert ranked[0].rank == 1 and ranked[0].of == 3


def test_missing_state_coordinate_yields_no_number():
    a = alignment("A", "N", "XX", 0.5, None)
    assert a.abs_gap is None and a.spec_score is None and a.crosses_over is None
