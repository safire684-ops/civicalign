"""Stable JSON output of the sections 2-5 findings.

This is what sections 2-5 owe the rest of the project: a fixed shape a frontend
can build against, which marks each figure publishable or not. A consumer that
respects `publishable` cannot accidentally display the committee drift metric,
which looks plausible and does not work.
"""
import json
from typing import Any

from .pipeline import Report


def to_dict(r: Report) -> dict[str, Any]:
    f, cl, ch = r.fit, r.chamber_lean, r.chamber
    slo, shi = f.slope_ci95
    klo, khi = cl.skew_range_points
    sig = [x for x in r.representation if x.is_significant]

    return {
        "meta": {
            "congress": r.config.congress,
            "score_column": r.config.score_column,
            "election_years": list(r.election.years),
            "senators_scored": len(r.scores),
            "scope": "math spec sections 2-5 (pillars 4, 5, 6)",
        },
        "chamber": {
            "publishable": True,
            "median": round(ch.median, 4),
            "cloture_pivot": round(ch.pivot, 4),
            "cloture_threshold": ch.pivot_n,
            "majority_party": ch.majority_party,
            "majority_median": round(ch.majority_median, 4),
            "minority_median": round(ch.minority_median, 4),
            "party_gap": round(ch.party_gap, 4),
        },
        "apportionment_skew": {
            "publishable": True,
            "points": round(cl.skew_points, 3),
            "range_points": [round(klo, 3), round(khi, 3)],
            "by_cycle_points": {str(y): round(v * 100, 3) for y, v in cl.by_year.items()},
            "senate_lean_pct": round(cl.senate_lean * 100, 3),
            "national_lean_pct": round(cl.national_lean * 100, 3),
            "units": "percentage points of two-party presidential vote share",
        },
        "state_alignment": {
            "publishable": True,
            "fit": {
                "slope": round(f.slope, 4),
                "intercept": round(f.intercept, 4),
                "r_squared": round(f.r_squared, 4),
                "slope_ci95": [round(slo, 4), round(shi, 4)],
                "residual_se": round(f.residual_se, 4),
                "significance_threshold": round(2 * f.residual_se, 3),
                "n": f.n,
            },
            "significant": [
                {
                    "bioguide": x.bioguide, "name": x.name, "state": x.state,
                    "party": x.party,
                    "state_lean_pct": round(x.state_lean * 100, 2),
                    "ideology": round(x.ideology, 4),
                    "predicted": round(x.predicted, 4),
                    "residual": round(x.residual, 4),
                    "t_stat": round(x.t_stat, 3),
                    "crosses_over": None,
                }
                for x in sig
            ],
            "n_significant": len(sig),
            "caveat": ("relative to the Senate-wide pattern, not an absolute "
                       "distance from the median voter"),
        },
        "committee_drift": {
            "publishable": False,
            "reason": ("0 of 19 survive validation: 17 medians move more than 0.05 "
                       "when one member leaves, most by 0.2-0.34, larger than the "
                       "drift values themselves; the other 2 are below the noise "
                       "floor. Tracks the party seat split, not ideology."),
            "committees": [
                {
                    "code": c.code, "ccd": round(c.ccd, 4),
                    "median": round(c.median, 4),
                    "split": [c.n_majority, c.n_minority],
                    "worst_one_member_shift": round(c.stability.worst_shift, 4),
                    "median_is_phantom": c.median_is_phantom,
                    "mean": round(c.mean, 4),
                    "ccd_mean": round(c.ccd_mean, 4),
                    "cnd_median": round(c.cnd, 4) if c.cnd is not None else None,
                    "cnd_mean": round(c.cnd_mean, 4) if c.cnd_mean is not None else None,
                    "publishable": not c.is_noise,
                }
                for c in r.committees
            ],
        },
        "committee_chairs": {
            "publishable": True,
            "note": "chair minus their own majority-party median on that committee",
            "chairs": sorted(
                [
                    {
                        "code": c.code,
                        "chair": round(c.chair_coord, 4),
                        "majority_median": round(c.majority_median, 4),
                        "gap": round(c.chair_coord - c.majority_median, 4),
                    }
                    for c in r.committees
                    if c.chair_coord is not None and c.majority_median is not None
                ],
                key=lambda d: -d["gap"],
            ),
        },
        "landmark_bills": {
            "publishable": True,
            "note": "median cutpoint of each bill's floor votes; where it divided the Senate",
            "bills": [{"key": l.key, "label": l.label, "cutpoint": round(l.cutpoint, 3),
                       "floor_votes": l.votes, "passed": l.passed} for l in r.landmarks],
        },
        "receipts": {
            "publishable": True,
            "note": ("one real vote per senator where they voted the opposite of the "
                     "side their state's position sits on; the bill's consequence in "
                     "plain English is Pillar 1's and is not supplied here"),
            "by_senator": {
                b: {"roll": x.roll, "date": x.date, "bill": x.bill, "label": x.label,
                    "question": x.question, "senator_vote": x.senator_vote,
                    "state_implied": x.state_implied, "cutpoint": round(x.cutpoint, 3)}
                for b, x in r.receipts.items()},
        },
        "committee_output_ideology": {
            "publishable": True,
            "note": "median cutpoint of floor votes on bills the committee reported out",
            "committees": [
                {"code": o.code, "floor_votes": o.n_votes, "coi": round(o.coi, 4),
                 "vs_senate": round(o.vs_senate, 4),
                 "vs_public": round(o.vs_public, 4) if o.vs_public is not None else None,
                 "publishable": o.is_reportable}
                for o in r.output_ideology],
        },
        "committee_gatekeeping": {
            "publishable": True,
            "note": ("survival rate of conservative-sponsored minus "
                     "liberal-sponsored bills, in percentage points; publish "
                     "gbi_vs_baseline, not gbi"),
            "baseline_points": round(r.gatekeeping_baseline, 3),
            "baseline_note": ("chamber-wide gap from majority control; already "
                              "subtracted in gbi_vs_baseline"),
            "committees": [
                {
                    "code": g.code,
                    "liberal_referred": g.lib_referred,
                    "liberal_reported": g.lib_reported,
                    "conservative_referred": g.con_referred,
                    "conservative_reported": g.con_reported,
                    "survival_liberal_pct": round(g.survival_liberal, 2),
                    "survival_conservative_pct": round(g.survival_conservative, 2),
                    "gbi": round(g.gbi, 3),
                    "gbi_vs_baseline": round(g.gbi_vs_baseline, 3),
                    "publishable": g.is_reportable,
                }
                for g in r.gatekeeping
            ],
        },
        "committee_state_lean": {
            "publishable": True,
            "note": "publish only entries where publishable is true",
            "committees": sorted(
                [
                    {
                        "code": c.code, "seats": c.n_seats,
                        "vs_nation_points": round(c.gap_points, 3),
                        "vs_senate_points": round(c.gap_vs_senate_points, 3),
                        "worst_one_member_shift_points": round(
                            c.worst_member_shift_points, 3),
                        "publishable": not c.is_fragile,
                    }
                    for c in r.committee_leans
                ],
                key=lambda d: -abs(d["vs_senate_points"]),
            ),
        },
    }


def to_json(r: Report, indent: int = 2) -> str:
    return json.dumps(to_dict(r), indent=indent)
