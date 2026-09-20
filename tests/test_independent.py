"""Recompute every published figure from the raw files, importing nothing from
civicalign except the Report under test.

A test that uses the pipeline's own helpers to check the pipeline cannot catch a
bug in those helpers. Everything below is computed from the downloaded files with
the standard library only, then compared.
"""
import csv
import json
import statistics as st

import pytest

from civicalign.config import DEFAULT
from civicalign.pipeline import run


@pytest.fixture(scope="module")
def report():
    return run(DEFAULT)


@pytest.fixture(scope="module")
def raw():
    """Senator coordinates, state centres and populations, read from scratch."""
    people = json.loads(DEFAULT.roster_json.read_text())
    roster = {
        p["id"]["bioguide"]: (
            p["name"].get("official_full") or p["name"]["last"],
            p["terms"][-1]["state"],
        )
        for p in people
        if p["terms"][-1]["type"] == "sen"
    }

    x = {}
    with DEFAULT.members_csv.open() as fh:
        for r in csv.DictReader(fh):
            if (r["chamber"] == "Senate" and r["congress"] == str(DEFAULT.congress)
                    and r["bioguide_id"] in roster and r["nokken_poole_dim1"]):
                x[r["bioguide_id"]] = float(r["nokken_poole_dim1"])

    s, pop = {}, {}
    with DEFAULT.ideology_tab.open() as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if int(r["presidential_year"]) == DEFAULT.ideology_year:
                a = r["abb"].strip().strip('"')
                s[a] = float(r["mrp_ideology"])
                pop[a] = int(r["population_2020"])

    return {"roster": roster, "x": x, "s": s, "pop": pop}


def test_exactly_one_hundred_senators_are_scored(raw, report):
    assert len(raw["roster"]) == 100
    assert len(raw["x"]) == 100
    assert set(raw["x"]) == set(report.scores)
    for b, v in raw["x"].items():
        assert report.scores[b] == pytest.approx(v)


def test_chamber_median_matches_a_hand_computation(raw, report):
    assert report.chamber.median == pytest.approx(st.median(raw["x"].values()))


def test_national_centre_matches_a_hand_computation(raw, report):
    """US_m is the population-weighted centre of the state estimates, DC included."""
    total = sum(raw["pop"][k] for k in raw["s"])
    expected = sum(raw["s"][k] * raw["pop"][k] for k in raw["s"]) / total
    assert report.chamber.national_coord == pytest.approx(expected)


def test_apportionment_skew_is_the_difference_of_those_two(raw, report):
    total = sum(raw["pop"][k] for k in raw["s"])
    us_m = sum(raw["s"][k] * raw["pop"][k] for k in raw["s"]) / total
    expected = st.median(raw["x"].values()) - us_m
    assert report.chamber.apportionment_skew == pytest.approx(expected)


def test_every_alignment_gap_and_score_is_correct(raw, report):
    """d_State(i,k) = |x_i - s_k| and AS_i = (1 - d/2) x 100, for all 100."""
    checked = 0
    for a in report.alignments:
        if a.abs_gap is None:
            continue
        xi = raw["x"][a.bioguide]
        sk = raw["s"][a.state]
        assert a.senator_coord == pytest.approx(xi)
        assert a.state_coord == pytest.approx(sk)
        assert a.abs_gap == pytest.approx(abs(xi - sk))
        assert a.spec_score == pytest.approx((1 - abs(xi - sk) / 2) * 100)
        checked += 1
    assert checked == 100


def test_alignment_ranking_is_ordered_by_gap(report):
    ranked = [a for a in report.alignments if a.rank]
    gaps = [a.abs_gap for a in sorted(ranked, key=lambda a: a.rank)]
    assert gaps == sorted(gaps, reverse=True)


def test_crosses_over_means_opposite_sides_of_centre(raw, report):
    for a in report.alignments:
        if a.state_coord is None:
            continue
        expected = (a.senator_coord > 0) != (a.state_coord > 0)
        assert a.crosses_over == expected


def test_committee_means_match_a_hand_computation(raw, report):
    members = json.loads(DEFAULT.committees_json.read_text())
    ch_mean = st.fmean(raw["x"].values())
    for c in report.committees:
        v = [raw["x"][m["bioguide"]] for m in members[c.code]
             if m.get("bioguide") in raw["x"]]
        assert c.mean == pytest.approx(st.fmean(v))
        assert c.ccd_mean == pytest.approx(st.fmean(v) - ch_mean)
        assert c.chamber_mean == pytest.approx(ch_mean)


def test_every_coordinate_is_inside_the_metric_space(raw):
    assert all(-1.0 <= v <= 1.0 for v in raw["x"].values())
    assert all(-1.0 <= v <= 1.0 for v in raw["s"].values())


def test_state_estimates_cover_every_state_with_senators(raw):
    senate_states = {stt for _, stt in raw["roster"].values()}
    assert len(senate_states) == 50
    assert senate_states <= set(raw["s"])
