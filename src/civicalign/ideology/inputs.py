"""Assemble the current inputs from the versioned tables and run Pillars 4-6.

    PYTHONPATH=src python -m civicalign.ideology.inputs

Prints the quantities with their units, status and input versions. Nothing
is stored here: versioned result records are Step 3 (compute.py).
"""
import json
import sys

from ..config import DEFAULT, Config
from . import bridge as B
from . import national as N
from . import pillars as P
from . import records as R
from .store import Table


def current_members(events: list[dict], congress: int) -> dict[str, list[str]]:
    """committee_id -> bioguide ids of members whose latest observed event is not a departure."""
    out: dict[str, list[str]] = {}
    for e in events:
        if e["congress"] == congress and e["event"] != "observed_left":
            out.setdefault(e["committee_id"], []).append(e["bioguide_id"])
    return {k: sorted(v) for k, v in out.items()}


def load(cfg: Config = DEFAULT) -> dict:
    t = {name: Table(cfg.ideology_dir, name) for name in R.TABLES}
    senators = [s for s in t["senator_ideology"].current() if s["congress"] == cfg.congress]
    publics = {r["geography_id"]: r for r in t["constituency_ideology"].current()
               if r["geography_type"] == "state" and r["wave"] == cfg.pillars_aip_wave}
    pops = {r["geography_id"]: r for r in t["state_population"].current()
            if r["measurement_year"] == cfg.pillar5_population_year and r["vintage"] == cfg.pillar5_population_vintage}
    events = t["committee_membership_events"].current()
    bridge = B.active(cfg, t["ideology_bridge"].current())

    def versions(rows):
        return sorted({(r["source_version"], r["retrieved_at"]) for r in rows})
    return {
        "senators": senators, "publics": publics, "populations": {k: v["population"] for k, v in pops.items()},
        "committees": current_members(events, cfg.congress), "bridge": bridge,
        "versions": {
            "congress": cfg.congress, "legislator_column": cfg.pillars_score_column,
            "legislator_model": versions(senators), "public_model": f"AIP wave {cfg.pillars_aip_wave}", "public_source": versions(publics.values()),
            "population": f"{cfg.pillar5_population_vintage}, {cfg.pillar5_population_year}", "population_source": versions(pops.values()),
            "committee_membership": versions(events), "bridge": bridge["bridge_version"], "bridge_status": bridge["status"],
            "weighting_method": cfg.pillar5_weighting_method,
        },
    }


def calculate(cfg: Config = DEFAULT) -> dict:
    x = load(cfg)
    col = cfg.pillars_score_column
    nat = N.national(x["bridge"])
    p5 = P.pillar5(x["senators"], x["populations"], nat, col, cfg.pillar5_weighting_method)
    return {
        "versions": x["versions"],
        "pillar4": P.pillar4(x["senators"], x["publics"], x["bridge"], col, cfg.pillars_aip_wave),
        "pillar5": p5,
        "pillar6": P.pillar6(x["committees"], x["senators"], p5["chamber_median"]["value"], nat, col),
    }


def main() -> int:
    print(json.dumps(calculate(DEFAULT), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
