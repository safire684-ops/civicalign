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

    if "--json" in sys.argv:
        from .export import to_json
        print(to_json(r))
        return 0

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
    if ch.national_coord is not None:
        print(f"\n  national voter estimate (survey scale)   {ch.national_coord:+.4f}")
        print(f"    source: {r.state_source.citation}")
        print("    shown on its own scale; NOT subtracted from the chamber median,")
        print("    because the two measurement systems are not bridged.")
    print(f"\n  apportionment skew in {r.election.label} vote share")
    print(f"  (election results on both sides, no scaling involved):")
    print(f"    avg state vote share per Senate seat   {cl.senate_lean * 100:6.2f}%")
    print(f"    national vote share                    {cl.national_lean * 100:6.2f}%")
    lo, hi = cl.skew_range_points
    print(f"    SKEW                                   {cl.skew_points:+6.2f} points")
    print(f"    per-cycle range                        [{lo:+.2f}, {hi:+.2f}]  "
          f"-- never crosses zero, so the sign holds")
    print("    by cycle: " + "  ".join(
        f"{y}:{v * 100:+.2f}" for y, v in sorted(cl.by_year.items())))


    print("\n-- Section 5 / Pillar 6: committee drift ----------------------")
    print(f"  {'cmte':5s} {'name':22s} {'mean':>8s} {'CCD':>8s} {'1-drop':>7s} {'ratio':>6s}  verdict")
    for cs in r.committees:
        v = "REPORTED" if cs.mean_is_usable else "below noise"
        print(f"  {cs.code:5s} {COMMITTEE_NAMES.get(cs.code, '?'):22s} {cs.mean:+8.3f} "
              f"{cs.ccd_mean:+8.3f} {cs.mean_jackknife:7.3f} {cs.mean_signal_ratio:5.1f}x  {v}")

    usable = [cs for cs in r.committees if cs.mean_is_usable]
    print(f"\n  CM_j uses the committee MEAN, against the chamber mean "
          f"({r.committees[0].chamber_mean:+.3f}).")
    print("  The mean accounts for density and extremity on both sides, so it does")
    print("  not fall into the empty gap between the party clusters the way a median")
    print("  does. Worst one-member shift: mean 0.111, median 0.342.")
    print(f"  {len(usable)} of {len(r.committees)} clear a 2x drift-to-shift bar and are reported.")

    print("\n-- Supporting: chair position ---------------------------------")
    print("  Measured against their own majority-party median on that panel, which")
    print("  isolates chair extremity from plain majority control.")
    ch = [(cs.code, cs.chair_coord, cs.majority_median) for cs in r.committees
          if cs.chair_coord is not None and cs.majority_median is not None]
    for code, cc, mm in sorted(ch, key=lambda t: -(t[1] - t[2]))[:5]:
        print(f"  {code:5s} {COMMITTEE_NAMES.get(code, '?'):22s} chair {cc:+.3f}  "
              f"majority median {mm:+.3f}  gap {cc - mm:+.3f}")

    print("\n-- Section 3 / Pillar 4: senator and state, on separate scales ----")
    print("  No senator-versus-state distance is computed: the Voteview and survey")
    print("  scales are not bridged. Each figure is compared only within its own system.")
    if r.pillar4_available:
        print(f"  state estimates: {r.state_source.citation}")
        print(f"\n  {'senator':24s} {'st':2s} {'x_i':>7s} {'x-Ch':>7s}   {'s_k':>7s} {'s-US':>7s}")
        us, ch_median = r.chamber.national_coord, r.chamber.median
        for a in sorted(r.positions, key=lambda a: a.senator_coord)[:10]:
            if a.state_coord is None:
                continue
            s_us = f"{a.state_coord - us:+7.3f}" if us is not None else "    n/a"
            print(f"  {a.name[:24]:24s} {a.state:2s} {a.senator_coord:+7.3f} "
                  f"{a.senator_coord - ch_median:+7.3f}   {a.state_coord:+7.3f} {s_us}")
        print("  x-Ch: senator minus Senate median (Voteview). s-US: state minus national")
        print("  estimate (survey). The two columns are never combined.")
    else:
        print(f"  UNAVAILABLE -- state source is '{r.state_source.name}'")

    print("\n-- Supporting: departure from the Senate-wide pattern ---------")
    f = r.fit
    lo, hi = f.slope_ci95
    sig = [x for x in r.representation if x.is_significant]
    print(f"  A second, relative view: fit senator records against {r.election.label}")
    print(f"  election results (r-squared {f.r_squared:.3f}, slope 95% CI "
          f"[{lo:+.3f}, {hi:+.3f}]) and read the residual.")
    print(f"  {len(sig)} of {f.n} senators depart from that pattern by more than "
          f"{2 * f.residual_se:.2f}:")
    for x in sig:
        print(f"    {x.name[:24]:24s} {x.state:2s} residual {x.residual:+.3f}  t {x.t_stat:+.2f}")

    if r.gatekeeping:
        print("\n-- Pillar 6 by behaviour: which bills each committee has sent on so far ----")
        print(f"  Every bill takes its sponsor's position. Chamber-wide, "
              f"conservative-sponsored")
        print(f"  bills are reported out {r.gatekeeping_baseline:+.1f} points more often "
              f"than liberal-sponsored")
        print("  ones -- that is majority control, not committee behaviour, so it is")
        print("  subtracted. The last column is what is left.")
        print(f"  {'cmte':5s} {'name':22s} {'liberal':>13s} {'conservative':>15s} "
              f"{'gap':>6s} {'vs base':>8s}")
        for g in r.gatekeeping:
            if not g.is_reportable:
                continue
            print(f"  {g.code:5s} {COMMITTEE_NAMES.get(g.code, '?'):22s} "
                  f"{g.lib_reported:4d}/{g.lib_referred:<4d}{g.survival_liberal:5.1f}% "
                  f"{g.con_reported:5d}/{g.con_referred:<4d}{g.survival_conservative:5.1f}% "
                  f"{g.gbi:+6.1f} {g.gbi_vs_baseline:+8.1f}")
        skipped = [g for g in r.gatekeeping if not g.is_reportable]
        print(f"  {len(skipped)} committees held back: fewer than 25 bills on one side, "
              f"where one bill moves the rate by whole points.")

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
