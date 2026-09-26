"""Regression tests for the bugs that silently corrupt numbers read from Voteview and the roster.

(The committee phantom-median and gatekeeping regressions went with the retired
Pillars 4-6 path. The Engine B committee median is checked by the supervisor and
tests/test_ideology_pillars.py; its known even-membership behaviour is documented
in the methodology registry.)

Both were found in real 119th Congress data. Neither raises an error on its own;
both just produce confident wrong numbers. Hence tests.
"""
import csv
import pytest

from civicalign.config import DEFAULT
from civicalign.sources import rosters, voteview
from statistics import median


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


def test_each_engine_uses_its_chosen_score_column():
    """nominate_dim1 is one career-long score; nokken_poole_dim1 moves each Congress.

    Murkowski is 0.204 in all ten of her Congresses on nominate_dim1. Pillars 4-6
    use nominate_dim1 by decision (a stable score on one scale for senators and the
    reference anchors; nokken_poole_dim1 is stored beside it as extra data only).
    The Pillar 1 floor-vote evidence (pipeline.py) keeps nokken_poole_dim1, which
    only orients each roll call's Yea side. Both columns must keep the property
    that motivates the choice.
    """
    assert DEFAULT.pillars_score_column == "nominate_dim1"
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
