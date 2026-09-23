"""Unit tests for the arithmetic of Sections 3-5, independent of real data."""
import pytest


from civicalign.alignment import positions
from civicalign.space import MAX_DISTANCE, nth_from_left


def test_even_count_median_averages_the_two_middles():
    """A 100-member chamber has no single middle member: the median must be the
    mean of the 50th and 51st, not the 50th alone."""
    from civicalign.space import median
    assert median([0.0, 0.2, 0.4, 0.6]) == pytest.approx(0.3)


def test_cloture_pivot_is_the_60th_from_the_left():
    vals = [i / 100 for i in range(100)]  # 0.00 .. 0.99
    assert nth_from_left(vals, 60) == 0.59


def test_positions_carry_both_numbers_and_nothing_derived():
    """The senator (Voteview) and state (survey) coordinates ride side by side.
    No gap, score, rank or crossing flag exists: the scales are not bridged."""
    a = positions("A", "N", "XX", senator_coord=0.7, state_coord=0.2)
    assert a.senator_coord == 0.7 and a.state_coord == 0.2
    for derived in ("abs_gap", "signed_gap", "spec_score", "rank", "crosses_over"):
        assert not hasattr(a, derived), derived


def test_missing_state_coordinate_yields_no_number():
    a = positions("A", "N", "XX", 0.5, None)
    assert a.state_coord is None
