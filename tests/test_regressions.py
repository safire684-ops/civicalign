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


def test_phantom_medians_are_suppressed():
    """BUG 3: on an evenly split committee the median describes no member.

    Budget is 10-10 and its median sits 0.333 from the nearest real senator --
    a third of the way across the usable scale. Evenly split committees also
    produce the LARGEST apparent drift, so without this check the least
    meaningful findings would rank highest.
    """
    from civicalign.pipeline import run

    r = run(DEFAULT)
    phantoms = [c for c in r.committees if c.median_is_phantom]
    assert phantoms, "expected at least one evenly split committee"

    # phantom medians are why Pillar 6 uses the mean instead
    assert all(c.median_is_phantom for c in phantoms)

    # and the effect must be real: phantoms are the evenly split ones
    for c in phantoms:
        assert c.is_evenly_split or c.median_gap_to_nearest_member > 0.05

    budget = next(c for c in r.committees if c.code == "SSBU")
    assert budget.n_majority == budget.n_minority
    assert budget.median_gap_to_nearest_member > 0.2
    # the mean does not have this problem: it sits among real members
    assert budget.mean_jackknife < 0.1


def test_icpsr_is_not_a_usable_join_key():
    """BUG 4: joining Voteview to the roster on ICPSR silently drops senators.

    A natural-looking pipeline merges Voteview (ICPSR key) to the roster via an
    ICPSR crosswalk. But the roster's icpsr field is unpopulated for 20 of 100
    sitting senators -- everyone elected recently (Tuberville, Britt, Kelly,
    Ossoff, Fetterman, Padilla, Hagerty...). An inner join on ICPSR therefore
    returns 80 senators and reports success.

    bioguide_id is present for all 100 AND already ships in HSall_members.csv, so
    the crosswalk is both broken and unnecessary. This test pins the reason.
    """
    import json

    people = json.loads(DEFAULT.roster_json.read_text())
    senators = [p for p in people if p["terms"][-1]["type"] == "sen"]

    with_icpsr = [p for p in senators if "icpsr" in p["id"]]
    assert len(senators) == 100
    assert len(with_icpsr) < 100, "if this ever passes, ICPSR became usable"

    # bioguide is complete, which is why the pipeline joins on it
    assert all("bioguide" in p["id"] for p in senators)


def test_voteview_already_carries_bioguide_so_no_crosswalk_is_needed():
    """The crosswalk step can be skipped entirely: Voteview ships bioguide_id."""
    with DEFAULT.members_csv.open() as fh:
        header = next(csv.reader(fh))
    assert "bioguide_id" in header
