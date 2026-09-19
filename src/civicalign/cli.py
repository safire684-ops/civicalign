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
    cl = r.chamber_lean
    print(f"\n  apportionment skew, measured in {r.election.year} vote share")
    print(f"  (both sides are election results, so no scale bridging is involved):")
    print(f"    avg state vote share per Senate seat   {cl.senate_lean * 100:6.2f}%")
    print(f"    national vote share                    {cl.national_lean * 100:6.2f}%")
    print(f"    SKEW                                   {cl.skew_points:+6.2f} points")
    if ch.apportionment_skew is not None:
        print(f"  apportionment skew in ideology units    {ch.apportionment_skew:+.4f}")
    else:
        print("  (the ideology-units version still needs bridged survey data)")

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

    print("\n-- Section 3 / Pillar 4: senator vs. their state --------------")
    f = r.fit
    print(f"  fitted on {f.year_note if hasattr(f, 'year_note') else r.election.year} results:"
          f"  ideology = {f.intercept:+.3f} {f.slope:+.3f} x state_vote_share")
    print(f"  r-squared {f.r_squared:.3f} over n={f.n}  "
          f"-- state election results explain {f.r_squared * 100:.0f}% of senator ideology")
    print("  residual = actual minus predicted. The two scales are never subtracted,")
    print("  so they never have to match. Positive = more conservative than the")
    print("  state's own election result predicts.")
    print(f"\n  {'':4s} {'senator':24s} {'st':2s} {'state%':>7s} {'ideol':>7s} {'pred':>7s} {'resid':>7s}")
    for x in r.representation[:10]:
        print(f"  #{x.rank:<3d} {x.name[:24]:24s} {x.state:2s} "
              f"{x.state_lean * 100:6.1f}% {x.ideology:+7.3f} {x.predicted:+7.3f} {x.residual:+7.3f}")
    print(f"  ... best matched: {r.representation[-1].name} "
          f"({r.representation[-1].state}, residual {r.representation[-1].residual:+.3f})")

    print("\n-- Committees vs. the public (vote share both sides) ----------")
    print(f"  'vs senate' strips out the {cl.skew_points:+.2f}pt structural skew and")
    print("  majority control, leaving the committee-specific part.")
    print(f"  {'cmte':5s} {'name':22s} {'seats':>5s} {'avg st%':>8s} {'vs nation':>10s} {'vs senate':>10s}")
    for x in sorted(r.committee_leans, key=lambda z: -abs(z.gap_vs_senate)):
        print(f"  {x.code:5s} {COMMITTEE_NAMES.get(x.code, '?'):22s} {x.n_seats:5d} "
              f"{x.mean_lean * 100:7.2f}% {x.gap_points:+9.2f} {x.gap_vs_senate_points:+10.2f}")

    print("\n-- Absolute distance to the median voter ----------------------")
    if not r.pillar4_available:
        print(f"  NOT AVAILABLE. State source = '{r.state_source.name}'.")
        print("  The regression above answers 'more extreme than their state predicts'.")
        print("  Answering 'how far from the median voter, in absolute terms' still")
        print("  needs bridged survey data -- see METHODOLOGY.md.")
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
