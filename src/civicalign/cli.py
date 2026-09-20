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
    print(f"\n  apportionment skew, measured in {r.election.label} avg vote share")
    print(f"  (both sides are election results, so no scale bridging is involved):")
    print(f"    avg state vote share per Senate seat   {cl.senate_lean * 100:6.2f}%")
    print(f"    national vote share                    {cl.national_lean * 100:6.2f}%")
    lo, hi = cl.skew_range_points
    print(f"    SKEW                                   {cl.skew_points:+6.2f} points")
    print(f"    per-cycle range                        [{lo:+.2f}, {hi:+.2f}]  "
          f"-- never crosses zero, so the sign holds")
    print("    by cycle: " + "  ".join(
        f"{y}:{v * 100:+.2f}" for y, v in sorted(cl.by_year.items())))
    if ch.apportionment_skew is not None:
        print(f"  apportionment skew in ideology units    {ch.apportionment_skew:+.4f}")
    else:
        print("  (the ideology-units version still needs bridged survey data)")

    print("\n-- Section 5 / Pillar 6: committee drift ----------------------")
    print(f"  {'cmte':5s} {'name':22s} {'split':>6s} {'median':>7s} {'CCD':>7s} "
          f"{'chair':>7s} {'ch-maj':>7s} {'verdict':<14s}")
    for cs in r.committees:
        chair = f"{cs.chair_coord:+.3f}" if cs.chair_coord is not None else "    n/a"
        cvm = (f"{cs.chair_coord - cs.majority_median:+.3f}"
               if cs.chair_coord is not None and cs.majority_median is not None else "    n/a")
        if cs.median_is_phantom:
            verdict = f"PHANTOM {cs.median_gap_to_nearest_member:.2f}"
        elif cs.is_noise:
            verdict = "below floor"
        else:
            verdict = "usable"
        print(f"  {cs.code:5s} {COMMITTEE_NAMES.get(cs.code, '?'):22s} "
              f"{cs.n_majority:2d}/{cs.n_minority:<3d} "
              f"{cs.median:+7.3f} {cs.ccd:+7.3f} {chair:>7s} {cvm:>7s} {verdict:<14s}")

    usable = [cs for cs in r.committees if not cs.is_noise]
    print(f"\n  *** {len(usable)} of {len(r.committees)} committee CCDs survive validation. ***")
    frag = [cs for cs in r.committees if cs.stability.is_fragile or cs.median_is_phantom]
    print(f"  {len(frag)} of {len(r.committees)} committee medians move more than 0.05 when one")
    print("  member leaves -- most move 0.2 to 0.34, LARGER than the CCD values")
    print("  themselves (0.01 to 0.31). With ~20 members split between two polarised")
    print("  clusters the median sits on the party boundary, so dropping anyone near")
    print("  it swings the result across the gap: CCD tracks the seat split, not")
    print(f"  ideology. The other {len(r.committees) - len(frag)} have stable medians but a CCD too small")
    print("  to clear the noise floor. Do not publish CCD. The measures below survive.")

    print("\n-- What survives: chair position ------------------------------")
    print("  A chair is one named person, so there is no median to destabilise.")
    print("  Measured against their own majority-party median on that panel, which")
    print("  isolates chair extremity from plain majority control.")
    ch = [(cs.code, cs.chair_coord, cs.majority_median) for cs in r.committees
          if cs.chair_coord is not None and cs.majority_median is not None]
    for code, cc, mm in sorted(ch, key=lambda t: -(t[1] - t[2]))[:5]:
        print(f"  {code:5s} {COMMITTEE_NAMES.get(code, '?'):22s} chair {cc:+.3f}  "
              f"majority median {mm:+.3f}  gap {cc - mm:+.3f}")

    print("\n-- Section 3 / Pillar 4: senator vs. their state --------------")
    f = r.fit
    print(f"  fitted on {r.election.label} average results:"
          f"  ideology = {f.intercept:+.3f} {f.slope:+.3f} x state_vote_share")
    lo, hi = f.slope_ci95
    print(f"  r-squared {f.r_squared:.3f} over n={f.n}  "
          f"-- state results explain {f.r_squared * 100:.0f}% of senator ideology")
    print(f"  slope 95% CI [{lo:+.3f}, {hi:+.3f}]  (excludes zero)   "
          f"residual SE {f.residual_se:.3f}")
    print("  residual = actual minus predicted. The two scales are never subtracted,")
    print("  so they never have to match. Positive = more conservative than the")
    print("  state's own election result predicts.")
    sig = [x for x in r.representation if x.is_significant]
    print(f"\n  {len(sig)} of {f.n} senators are further from their state's pattern than")
    print("  chance comfortably explains (|t| > 2). Ranked by t, not raw residual:")
    print(f"  {'':4s} {'senator':24s} {'st':2s} {'state%':>7s} {'resid':>7s} {'t':>6s}")
    for x in sig:
        print(f"  #{x.rank:<3d} {x.name[:24]:24s} {x.state:2s} "
              f"{x.state_lean * 100:6.1f}% {x.residual:+7.3f} {x.t_stat:+6.2f}")
    print(f"\n  The other {f.n - len(sig)} sit where their state's results predict. A residual")
    print(f"  needs to clear roughly {2 * f.residual_se:.2f} to mean anything, so a top-ten")
    print("  list ranked by raw residual would mostly be noise.")

    print("\n-- Committees vs. the public (vote share both sides) ----------")
    print(f"  'vs senate' strips out the {cl.skew_points:+.2f}pt structural skew and")
    print("  majority control, leaving the committee-specific part.")
    print("  A mean over ~20 states, which is far steadier than a median over the")
    print("  same members -- but small panels still fail: 'shift' is how far one")
    print("  departure moves the gap, and must be smaller than the gap itself.")
    print(f"  {'cmte':5s} {'name':22s} {'seats':>5s} {'vs nation':>10s} {'vs senate':>10s} "
          f"{'shift':>7s} {'verdict':<8s}")
    for x in sorted(r.committee_leans, key=lambda z: -abs(z.gap_vs_senate)):
        v = "fragile" if x.is_fragile else "holds"
        print(f"  {x.code:5s} {COMMITTEE_NAMES.get(x.code, '?'):22s} {x.n_seats:5d} "
              f"{x.gap_points:+10.2f} {x.gap_vs_senate_points:+10.2f} "
              f"{x.worst_member_shift_points:7.2f} {v:<8s}")

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
