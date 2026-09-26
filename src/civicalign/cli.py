"""python -m civicalign [--json]

Prints the latest saved Pillars 4-6 result record (nothing is recalculated
here) and the commands that produce it. --json prints the record itself.
"""
import json
import sys

from .build_pages import fmt
from .config import DEFAULT
from .ideology import compute as C
from .ideology.store import Table

COMMANDS = """
Commands (PYTHONPATH=src):
  python -m civicalign.agents                 fetch the source snapshot (all or nothing)
  python -m civicalign.agents.verify          check the snapshot
  python -m civicalign.ideology.ingest        versioned inputs (--dry-run)
  python -m civicalign.ideology.bridge        record the none-v0 bridge
  python -m civicalign.ideology.anchors       record the three Pillar 4 reference anchors
  python -m civicalign.ideology.compute       versioned results (--verify, --full)
  python -m civicalign.build_pages            build demo/senator-check.html and demo/methodology.html (--check)
  python -m civicalign.agents.supervisor      independent recount of every published number
"""


def _v(q: dict) -> str:
    """The page's own rounding (half-up, 3 decimals), so the two never disagree."""
    return fmt(q["value"], 3, signed=True) if q["status"] != "NOT_AVAILABLE" else "not available"


def main() -> int:
    idx = C.index(DEFAULT)
    if not idx:
        print("no saved Pillars 4-6 result: run ingest, bridge, anchors and compute" + COMMANDS)
        return 1
    rec = C.load_record(DEFAULT, idx[-1]["input_key"])
    if "--json" in sys.argv:
        print(json.dumps(rec, indent=1, sort_keys=True))
        return 0
    v, p5, p6 = rec["versions"], rec["results"]["pillar5"], rec["results"]["pillar6"]
    names = {r["committee_id"]: r["display_name"] for r in Table(DEFAULT.ideology_dir, "committee_names").current()}
    print(f"CivicAlign Pillars 4-6  |  {v['congress']}th Congress  |  {v['legislator_model']['score_column']}  |  "
          f"record {rec['input_key'][:8]}  |  measured {v['measurement_date']}")
    print(f"\nPillar 5 ({p5['configured_method']}, candidate method, not final)  {p5['active_senators']} senators")
    print(f"  each senator counted equally       {_v(p5['plain_center'])}")
    print(f"  population-weighted                {_v(p5['population_weighted_center'])}")
    print(f"  difference (plain - weighted)      {_v(p5['population_weighting_difference'])}")
    print(f"  Senate median (details)            {_v(p5['details']['chamber_median'])}")
    print(f"  national public / Senate-public    {_v(p5['national_public'])} / {_v(p5['chamber_public_gap'])}")
    print("\nPillar 6: committee median and committee - Senate median")
    for code in sorted(p6, key=lambda c: names.get(c, c)):
        c = p6[code]
        print(f"  {names.get(code, code):45s} {code}  {_v(c['committee_median'])}  {_v(c['committee_senate_drift'])}  "
              f"({c['members_scored']} of {c['members_listed']} members scored)")
    print("\nPillar 4: senator scores beside state public estimates; senator-to-state distance not available (bridge "
          f"{v['bridge']['bridge_version']}, status {v['bridge']['status']}).")
    print(COMMANDS)
    return 0
