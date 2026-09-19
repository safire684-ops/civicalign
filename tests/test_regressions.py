"""Regression tests for the two bugs that silently corrupt published numbers.

Both were found in real 119th Congress data. Neither raises an error on its own;
both just produce confident wrong numbers. Hence tests.
"""
import csv
import pytest

from civicalign.config import DEFAULT
from civicalign.sources import rosters, voteview
from civicalign.space import median


def test_roster_is_exactly_100():
    roster = rosters.load_current_senators(DEFAULT.roster_json)
    assert len(roster) == 100


def test_seat_dedupe_drops_departed_members():
    """BUG 1: filtering Voteview on congress alone gives 104 rows for 100 seats.

    FL, OH, OK and SC each carry a departed member alongside their replacement.
    All four extras are Republicans, so the naive median lands at +0.3645 instead
    of the correct +0.3100 -- a 0.045 artifact, which is a large fraction of an
    apportionment skew that is itself only 0.1-0.3 wide.
    """
    roster = rosters.load_current_senators(DEFAULT.roster_json)

    naive = []
    with DEFAULT.members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if (row["chamber"] == "Senate"
                    and row["congress"] == str(DEFAULT.congress)
                    and row[DEFAULT.score_column]):
                naive.append(float(row[DEFAULT.score_column]))

    deduped = voteview.load_scores(
        DEFAULT.members_csv, DEFAULT.congress, roster, DEFAULT.score_column
    )

    assert len(naive) > 100, "fixture changed: expected surplus rows in the raw file"
    assert len(deduped) == 100
    assert abs(median(naive) - median(deduped.values())) > 0.01, (
        "the dedupe must actually move the median, or this guard is untested"
    )


def test_score_column_is_not_the_frozen_one():
    """BUG 2: nominate_dim1 never changes over a career.

    Murkowski is 0.204 in all ten of her Congresses. Building Pillar 4 on it
    freezes every alignment gap for life and flattens every time series.
    nokken_poole_dim1 is the per-Congress column that actually moves.
    """
    assert DEFAULT.score_column == "nokken_poole_dim1"

    dw, np_ = set(), set()
    with DEFAULT.members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["chamber"] == "Senate" and row["bioguide_id"] == "M001153":
                if row["nominate_dim1"]:
                    dw.add(row["nominate_dim1"])
                if row["nokken_poole_dim1"]:
                    np_.add(row["nokken_poole_dim1"])

    assert len(dw) == 1, "nominate_dim1 unexpectedly varies -- recheck the premise"
    assert len(np_) > 1, "nokken_poole_dim1 must vary or it buys us nothing"


def test_coordinates_stay_inside_the_metric_space():
    roster = rosters.load_current_senators(DEFAULT.roster_json)
    scores = voteview.load_scores(
        DEFAULT.members_csv, DEFAULT.congress, roster, DEFAULT.score_column
    )
    assert all(-1.0 <= v <= 1.0 for v in scores.values())


def test_seat_guard_rejects_a_crowded_state():
    """The guard must fail loudly rather than average a phantom senator in."""
    roster = rosters.load_current_senators(DEFAULT.roster_json)
    fake = dict(roster)
    victim = next(iter(roster.values()))
    for i in range(2):
        key = f"FAKE{i}"
        fake[key] = rosters.Senator(key, f"Phantom {i}", victim.state, "Republican")
    with pytest.raises(voteview.SeatCountError):
        voteview._validate({k: 0.1 for k in fake}, fake)
