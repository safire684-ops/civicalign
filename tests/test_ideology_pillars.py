"""Pillars 4-6, Step 2: the bridge, the national estimate, and the three pillars.

Fixture senators here are invented (FIXTURE names, states ZA..ZD) and every
expected number is worked out by hand in the comments. Real-data tests
recompute the published quantities from the raw files with separate code."""
import csv
import dataclasses
import json
import statistics
from fractions import Fraction
from pathlib import Path

import pytest

from civicalign.config import DEFAULT
from civicalign.ideology import bridge as B
from civicalign.ideology import national as N
from civicalign.ideology import pillars as P
from civicalign.ideology import records as R
from civicalign.ideology.inputs import calculate, load
from civicalign.ideology.store import Table

ROOT = Path(__file__).resolve().parents[1]
COL = "nominate_dim1"


def sen(b, state, score, seated=True, nokken=None):
    return {"bioguide_id": b, "name": f"FIXTURE Senator {b}", "state": state, "seated": seated, "nominate_dim1": score,
            "nokken_poole_dim1": nokken if nokken is not None else score, "congress": 119}


# FIXTURE Senate: ZA (population 1000) two senators; ZB (100) two; ZC (300) one seat vacant; plus a departed member
SENATE = [sen("FXA1", "ZA", -0.4), sen("FXA2", "ZA", -0.2), sen("FXB1", "ZB", 0.5), sen("FXB2", "ZB", 0.7),
          sen("FXC1", "ZC", 0.1), sen("FXOLD", "ZB", 0.9, seated=False)]
POPS = {"ZA": 1000, "ZB": 100, "ZC": 300}
NONE = B.NONE_V0
NAT = N.national(NONE)


# ---- the bridge and the national estimate ---------------------------------------------------

def test_the_only_bridge_is_none_and_it_converts_nothing():
    assert R.validate("ideology_bridge", NONE) == [] and NONE["status"] == "NONE"
    assert B.METHODS == {}, "no senator-to-voter conversion method exists"
    r = B.to_common(NONE, 0.12, 0.05)
    assert r["value"] is None and r["status"] == "NOT_AVAILABLE" and "status NONE" in r["reason"]
    prov = {**NONE, "bridge_version": "FIXTURE-prov", "status": "PROVISIONAL", "public_model_version": "FIXTURE",
            "legislator_model_version": "FIXTURE", "transformation_method": "FIXTURE-affine", "transformation_parameters": {"a": 1.0}}
    r = B.to_common(prov, 0.12, 0.05)
    assert r["status"] == "NOT_AVAILABLE" and "not implemented" in r["reason"], "a named but unimplemented method is never guessed"
    with pytest.raises(B.BridgeError):
        B.active(dataclasses.replace(DEFAULT, active_bridge_version="FIXTURE-missing"), [NONE])


def test_the_national_estimate_is_unresolved():
    n = N.national(NONE)
    assert n["value"] is None and n["status"] == "NOT_AVAILABLE" and n["definition_status"] == "UNRESOLVED"
    assert "population-weighted mean of state estimates" in n["reason"], "the candidates are named, none chosen"


# ---- Pillar 5 -----------------------------------------------------------------------------------

def test_weights_split_a_state_across_its_seated_senators():
    active, _ = P.split_active(SENATE, COL)
    w = P.senator_weights(active, POPS)
    assert w == {"FXA1": Fraction(500), "FXA2": Fraction(500), "FXB1": Fraction(50), "FXB2": Fraction(50), "FXC1": Fraction(300)}
    assert "FXOLD" not in w, "a departed member carries no weight"
    with pytest.raises(P.InputError, match="no population"):
        P.senator_weights(active, {"ZA": 1000})


@pytest.mark.parametrize("points,expected", [
    ([(-0.5, 1), (0.1, 1), (0.4, 1), (0.6, 1)], 0.25),   # half = 2 reached exactly at 0.1 -> average with 0.4 (ordinary median)
    ([(-0.5, 3), (0.1, 1), (0.4, 1)], -0.5),              # half = 2.5 passed at the first point
    ([(0.9, 1), (-0.2, 1), (0.3, 2)], 0.3),               # unsorted input; half = 2; cum 1, then 3 > 2 at 0.3
    ([(0.2, Fraction(1, 3)), (0.4, Fraction(1, 3)), (0.8, Fraction(2, 3))], 0.6),   # half = 2/3 exactly at 0.4 -> (0.4 + 0.8) / 2
])
def test_weighted_median_v1(points, expected):
    assert P.weighted_median_v1([(x, Fraction(w)) for x, w in points]) == pytest.approx(expected)


def test_pillar5_main_comparison_is_the_mean_by_hand():
    p = P.pillar5(SENATE, POPS, NAT, COL, "population_weighted_mean_v1")
    assert p["active_senators"] == 5 and p["configured_method"] == "population_weighted_mean_v1"
    # plain mean (-0.4 - 0.2 + 0.1 + 0.5 + 0.7) / 5 = 0.14
    assert p["plain_center"]["value"] == pytest.approx(0.14) and p["plain_center"]["statistic"] == "chamber_mean"
    # weights 500, 500, 300, 50, 50: (-200 - 100 + 30 + 25 + 35) / 1400 = -0.15
    assert p["population_weighted_center"]["value"] == pytest.approx(-0.15)
    # population weighting difference = plain mean - weighted mean = 0.14 - (-0.15) = +0.29, sign kept
    assert p["population_weighting_difference"]["value"] == pytest.approx(0.29)
    assert p["population_weighted_center"]["role"] == "PRIMARY"
    assert p["population_weighted_center"]["method_status"] == "CANDIDATE_METHOD_NOT_FINAL"
    assert p["national_public"]["status"] == "NOT_AVAILABLE" and p["chamber_public_gap"]["status"] == "NOT_AVAILABLE"
    quantities = [v for k, v in p.items() if isinstance(v, dict) and k not in ("national_public", "details")]
    quantities += [p["details"]["chamber_median"], p["details"]["chamber_mean"]]
    quantities += [q for c in p["details"]["methods"].values() for q in c.values()]
    assert quantities and all(v["units"].startswith("Voteview") for v in quantities)
    with pytest.raises(P.InputError, match="unknown weighting method"):
        P.pillar5(SENATE, POPS, NAT, COL, "population_weighted_mode")


def test_pillar5_median_is_kept_in_details_by_hand():
    p = P.pillar5(SENATE, POPS, NAT, COL, "population_weighted_mean_v1")
    d = p["details"]
    assert "chamber_median" not in p and "chamber_mean" not in p, "medians and means sit under details; the headline is the primary method"
    # active scores -0.4, -0.2, 0.1, 0.5, 0.7 -> median 0.1
    assert d["chamber_median"]["value"] == pytest.approx(0.1) and d["chamber_mean"]["value"] == pytest.approx(0.14)
    med = d["methods"]["population_weighted_median_v1"]
    # weights 500, 500, 300, 50, 50 (total 1400, half 700): cumulative 500 at -0.4, 1000 at -0.2 -> centre -0.2
    # difference = plain median - weighted median = 0.1 - (-0.2) = +0.3
    assert (med["plain_center"]["value"], med["population_weighted_center"]["value"], med["population_weighting_difference"]["value"]) \
        == pytest.approx((0.1, -0.2, 0.3))
    assert med["plain_center"]["statistic"] == "chamber_median" and med["population_weighted_center"]["role"] == "SECONDARY_COMPARISON"
    assert d["methods"]["population_weighted_mean_v1"]["population_weighting_difference"] == p["population_weighting_difference"]
    q = P.pillar5(SENATE, POPS, NAT, COL, "population_weighted_median_v1")
    assert q["details"]["methods"] == d["methods"], "both methods are computed whichever is configured"
    assert q["population_weighted_center"]["value"] == pytest.approx(-0.2) and q["population_weighting_difference"]["value"] == pytest.approx(0.3)


@pytest.mark.parametrize("points,expected", [
    ([(1.0, 1), (0.0, 3)], 0.25),                                  # (1*1 + 0*3) / 4
    ([(-0.4, 2), (0.6, 2)], 0.1),                                  # equal weights: the plain mean
    ([(0.3, Fraction(1, 3)), (-0.3, Fraction(2, 3))], -0.1),       # (0.1 - 0.2) / 1
])
def test_weighted_mean_v1(points, expected):
    assert P.weighted_mean_v1([(x, Fraction(w)) for x, w in points]) == pytest.approx(expected)
    with pytest.raises(P.InputError):
        P.weighted_mean_v1([])


def test_pillar5_leaves_out_unscored_senators_and_can_use_the_other_column():
    s = SENATE + [sen("FXD1", "ZC", None)]
    s[-1]["nokken_poole_dim1"] = None
    p = P.pillar5(s, POPS, NAT, COL, "population_weighted_mean_v1")
    assert p["unscored_seated_senators"] == ["FXD1"] and p["active_senators"] == 5
    # with ZC now holding two seated senators, FXC1 carries 150: weights 500,500,150,50,50 (total 1250)
    # weighted mean (-200 - 100 + 15 + 25 + 35) / 1250 = -0.18; weighted median: half 625, cumulative 1000 at -0.2 -> -0.2
    assert p["population_weighted_center"]["value"] == pytest.approx(-0.18)
    assert p["details"]["methods"]["population_weighted_median_v1"]["population_weighted_center"]["value"] == pytest.approx(-0.2)
    alt = [dict(x, nokken_poole_dim1=x["nominate_dim1"] + 0.1) for x in SENATE]
    q = P.pillar5(alt, POPS, NAT, "nokken_poole_dim1", "population_weighted_mean_v1")
    assert q["plain_center"]["value"] == pytest.approx(0.24) and "nokken_poole_dim1" in q["plain_center"]["units"]


# ---- Pillar 4 -----------------------------------------------------------------------------------

def test_pillar4_keeps_the_two_scales_apart_and_computes_no_distance():
    publics = {"ZA": {"estimate": 0.12, "standard_error": 0.05, "survey_period": "FIXTURE"}}
    rows = {r["bioguide_id"]: r for r in P.pillar4(SENATE + [sen("FXD1", "ZD", None)], publics, NONE, COL, 2020)}
    assert set(rows) == {"FXA1", "FXA2", "FXB1", "FXB2", "FXC1", "FXD1"}, "seated senators only"
    a = rows["FXA1"]
    assert a["senator_score"]["value"] == -0.4 and a["state_public_estimate"]["value"] == 0.12
    assert a["state_public_estimate"]["standard_error"] == 0.05
    assert a["senator_score"]["units"] != a["state_public_estimate"]["units"] and "not the Voteview scale" in a["state_public_estimate"]["units"]
    assert a["state_on_senator_scale"]["status"] == "NOT_AVAILABLE" and a["distance"]["status"] == "NOT_AVAILABLE"
    assert a["distance"]["value"] is None and "NONE" in a["distance"]["reason"]
    assert rows["FXB1"]["state_public_estimate"]["status"] == "NOT_AVAILABLE", "no AIP estimate for ZB"
    assert rows["FXD1"]["senator_score"]["status"] == "NOT_AVAILABLE", "an unscored senator gets no number"


# ---- Pillar 6 -----------------------------------------------------------------------------------

def test_pillar6_by_hand():
    committees = {"SSZA": ["FXA1", "FXB1", "FXC1"], "SSZB": ["FXA1", "FXA2", "FXB1", "FXB2"], "SSZC": ["FXOLD"]}
    out = P.pillar6(committees, SENATE, 0.1, NAT, COL)
    # SSZA: -0.4, 0.5, 0.1 -> median 0.1; drift 0.1 - 0.1 = 0
    assert out["SSZA"]["committee_median"]["value"] == pytest.approx(0.1) and out["SSZA"]["committee_senate_drift"]["value"] == pytest.approx(0.0)
    # SSZB: -0.4, -0.2, 0.5, 0.7 -> median (-0.2 + 0.5) / 2 = 0.15; drift +0.05
    assert out["SSZB"]["committee_median"]["value"] == pytest.approx(0.15) and out["SSZB"]["committee_senate_drift"]["value"] == pytest.approx(0.05)
    assert out["SSZC"]["committee_median"]["status"] == "NOT_AVAILABLE" and out["SSZC"]["members_left_out"] == ["FXOLD"], \
        "a member no longer seated is left out and named"
    assert all(c["committee_public_drift"]["status"] == "NOT_AVAILABLE" for c in out.values())


def test_config_defaults_are_the_decided_ones():
    assert DEFAULT.pillars_score_column == "nominate_dim1"
    assert DEFAULT.active_bridge_version == "none-v0"
    assert DEFAULT.pillar5_weighting_method in P.WEIGHTING_METHODS
    assert DEFAULT.pillar5_weighting_method == "population_weighted_mean_v1", "the weighted mean is the primary method"
    assert P.WEIGHTING_METHODS["population_weighted_mean_v1"]["role"] == "PRIMARY"
    assert P.WEIGHTING_METHODS["population_weighted_median_v1"]["role"] == "SECONDARY_COMPARISON"
    assert set(P.WEIGHTING_METHODS) == {"population_weighted_median_v1", "population_weighted_mean_v1"}
    assert all(m["status"] == "CANDIDATE_METHOD_NOT_FINAL" for m in P.WEIGHTING_METHODS.values())


def test_nothing_is_rescaled_to_0_100():
    import re
    for f in (ROOT / "src" / "civicalign" / "ideology").glob("*.py"):
        assert not re.search(r"\*\s*50\s*\+\s*50|0\s*(?:-|to)\s*100", f.read_text()), f.name


# ---- the real snapshot, recomputed independently ----------------------------------------------------

@pytest.fixture(scope="module")
def real():
    if not (DEFAULT.ideology_dir / "senator_ideology.jsonl").exists():
        pytest.skip("no Pillars 4-6 tables")
    return calculate(DEFAULT)


def _seated_scores_from_raw():
    seated = {p["id"]["bioguide"]: p["terms"][-1]["state"] for p in json.loads(DEFAULT.roster_json.read_text()) if p["terms"][-1]["type"] == "sen"}
    scores = {}
    with DEFAULT.members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["chamber"] == "Senate" and row["congress"] == str(DEFAULT.congress) and row["bioguide_id"] in seated and row["nominate_dim1"]:
                scores[row["bioguide_id"]] = float(row["nominate_dim1"])
    return seated, scores


def test_real_pillar5_recomputes_from_raw_files(real):
    seated, scores = _seated_scores_from_raw()
    p5 = real["pillar5"]
    assert p5["details"]["chamber_median"]["value"] == pytest.approx(statistics.median(scores.values()))
    assert p5["plain_center"]["value"] == pytest.approx(statistics.fmean(scores.values()))
    pops = {}
    with DEFAULT.population_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["SUMLEV"] == "040":
                pops[row["NAME"]] = int(row["POPESTIMATE2024"])
    from civicalign.sources.population import USPS
    pop = {USPS[n]: v for n, v in pops.items() if n in USPS}
    count = {}
    for b in scores:
        count[seated[b]] = count.get(seated[b], 0) + 1
    # independent: integer weights (pop * 2 / seats), a weighted mean, and a walk to half for the weighted median
    pts = sorted((scores[b], pop[seated[b]] * 2 // count[seated[b]]) for b in scores)
    tot = sum(w for _, w in pts)
    wmean = sum(x * w for x, w in pts) / tot
    assert p5["population_weighted_center"]["value"] == pytest.approx(wmean)
    assert p5["population_weighting_difference"]["value"] == pytest.approx(statistics.fmean(scores.values()) - wmean)
    acc, centre = 0, None
    for i, (x, w) in enumerate(pts):
        acc += w
        if 2 * acc == tot:
            centre = (x + pts[i + 1][0]) / 2; break
        if 2 * acc > tot:
            centre = x; break
    med = p5["details"]["methods"]["population_weighted_median_v1"]
    assert med["population_weighted_center"]["value"] == pytest.approx(centre)
    assert med["population_weighting_difference"]["value"] == pytest.approx(statistics.median(scores.values()) - centre)
    assert p5["chamber_public_gap"]["value"] is None and real["versions"]["bridge_status"] == "NONE"


def test_real_pillar6_and_pillar4(real):
    seated, scores = _seated_scores_from_raw()
    raw = json.loads(DEFAULT.committees_json.read_text())
    for cid in ("SSFR", "SSAP", "SSEV"):
        members = [m["bioguide"] for m in raw[cid] if m.get("bioguide") in scores]
        med = statistics.median(scores[b] for b in members)
        c = real["pillar6"][cid]
        assert c["committee_median"]["value"] == pytest.approx(med) and c["members_scored"] == len(members)
        assert c["committee_senate_drift"]["value"] == pytest.approx(med - statistics.median(scores.values()))
    assert set(real["pillar6"]) == {c for c in raw if c.startswith("SS") and len(c) == 4}
    p4 = real["pillar4"]
    assert len(p4) == 100 and all(r["distance"]["status"] == "NOT_AVAILABLE" for r in p4)
    assert all(r["state_public_estimate"]["status"] == "AVAILABLE" and r["state_public_estimate"]["standard_error"] > 0 for r in p4)


def test_committed_bridge_table_holds_only_none():
    t = Table(DEFAULT.ideology_dir, "ideology_bridge")
    if not t.path.exists():
        pytest.skip("bridge table not written")
    assert t.verify() == [] and [b["bridge_version"] for b in t.current()] == ["none-v0"]
    assert B.active(DEFAULT)["status"] == "NONE"
