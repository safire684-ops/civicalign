"""python -m civicalign"""
import sys

from .config import DEFAULT
from .pipeline import run

COMMITTEE_NAMES = {
    "SSAF": "Agriculture", "SSAP": "Appropriations", "SSAS": "Armed Services",
    "SSBK": "Banking", "SSBU": "Budget", "SSCM": "Commerce", "SSEG": "Energy",
    "SSEV": "Environment", "SSFI": "Finance", "SSFR": "Foreign Relations",
    "SSGA": "Homeland/Govt Affairs", "SSHR": "HELP", "SSJU": "Judiciary",
    "SSRA": "Rules", "SSSB": "Small Business", "SSVA": "Veterans",
    "SLET": "Ethics (select)", "SLIN": "Intelligence (select)",
    "SLIA": "Indian Affairs (select)", "SLAG": "Aging (select)",
}


def main() -> int:
    r = run(DEFAULT)
    c = r.config

    print(f"CivicAlign  |  {c.congress}th Congress  |  score column: {c.score_column}")
    print(f"senators scored: {len(r.scores)} of {len(r.senators)} seated", end="")
    print(f"   (unscored: {[s.name for s in r.unscored]})" if r.unscored else "")

    ch = r.chamber
    print("\n-- Section 4 / Pillar 5: chamber ------------------------------")
    print(f"  chamber median                {ch.median:+.4f}")
    print(f"  {ch.pivot_n}th-vote pivot (cloture)    {ch.pivot:+.4f}"
          f"   [{ch.pivot - ch.median:+.3f} vs median]")
    print(f"  majority ({ch.majority_party}) median   {ch.majority_median:+.4f}")
    print(f"  minority median               {ch.minority_median:+.4f}")
    print(f"  party gap (polarization)       {ch.party_gap:.4f}")
    if ch.apportionment_skew is None:
        print("  apportionment skew            UNAVAILABLE -- no bridged national coordinate")
    else:
        print(f"  apportionment skew            {ch.apportionment_skew:+.4f}")

    print("\n-- Section 5 / Pillar 6: committee drift ----------------------")
    print(f"  {'cmte':5s} {'name':22s} {'n':>3s} {'median':>7s} {'CCD':>7s} "
          f"{'chair':>7s} {'ch-cm':>7s} {'spread':>6s}")
    for cs in r.committees:
        flag = "  (noise)" if cs.is_noise else ""
        chair = f"{cs.chair_coord:+.3f}" if cs.chair_coord is not None else "    n/a"
        cvc = f"{cs.chair_vs_committee:+.3f}" if cs.chair_vs_committee is not None else "    n/a"
        print(f"  {cs.code:5s} {COMMITTEE_NAMES.get(cs.code, '?'):22s} {cs.n_scored:3d} "
              f"{cs.median:+7.3f} {cs.ccd:+7.3f} {chair:>7s} {cvc:>7s} {cs.spread:6.2f}{flag}")

    n_noise = sum(1 for cs in r.committees if cs.is_noise)
    print(f"  {n_noise} of {len(r.committees)} committees have CCD below the "
          f"{c.ccd_noise_floor} noise floor -- not findings.")

    print("\n-- Section 3 / Pillar 4: senator vs. state --------------------")
    if not r.pillar4_available:
        print(f"  UNAVAILABLE. State source = '{r.state_source.name}' ({r.state_source.citation}).")
        print("  This is the bridging blocker, not a bug: senator scores and survey")
        print("  scales are different rulers. Configure a bridged source to enable.")
    else:
        label = "" if r.state_source.is_bridged else "  [PROXY - NOT A REAL BRIDGE]"
        print(f"  source: {r.state_source.name}{label}")
        for a in r.alignments[:10]:
            if a.abs_gap is None:
                continue
            x = " CROSSES OVER" if a.crosses_over else ""
            print(f"  #{a.rank:3d}/{a.of}  {a.name:28s} {a.state}  "
                  f"gap {a.signed_gap:+.3f}  spec score {a.spec_score:5.1f}%{x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
