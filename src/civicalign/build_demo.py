"""Regenerate the demo page's embedded data from the current pipeline.

WHY THIS STEP EXISTS
--------------------
demo/senator-check.html carries its data inside itself, so it opens from a file
with no server. That also means fresh source data does NOT reach the page until
this runs. Without it the update chain stops one step short: the numbers change,
the tests notice, and the page still shows last week's figures.

This replaces only the four data blocks. Layout, copy and styling are left
untouched, so the page can be edited by hand without this overwriting the edits.
"""
import json
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

from .config import DEFAULT, Config
from .pipeline import Report, run

DEMO = Path(__file__).resolve().parents[2] / "demo" / "senator-check.html"
REPORT_TEMPLATE = DEMO.parent / "methodology.template.html"
REPORT = DEMO.parent / "methodology.html"

NUMBER_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven",
                "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen",
                "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen", "Twenty"]


def _signed(v: float, places: int = 3) -> str:
    """+0.310 / &minus;0.547 -- the report's own typography for signed figures."""
    text = f"{abs(v):.{places}f}"
    return ("+" if v >= 0 else "&minus;") + text


def _p100(v: float, places: int = 1) -> str:
    """A position on the reader's 0-100 scale: score * 50 + 50."""
    return f"{v * 50 + 50:.{places}f}"


def _d100(v: float, places: int = 1) -> str:
    """A distance on the reader's 0-100 scale: raw distance * 50, unsigned."""
    return f"{abs(v) * 50:.{places}f}"


def _sd100(v: float, places: int = 1) -> str:
    """A signed distance on the 0-100 scale, with the report's minus sign."""
    return ("+" if v >= 0 else "&minus;") + _d100(v, places)


def _report_values(r: Report) -> dict[str, str]:
    from datetime import date

    scored = [a for a in r.positions if a.state_coord is not None]
    os_ = next(a for a in scored if a.bioguide == "O000174")

    rows = [g for g in r.gatekeeping if g.is_reportable]
    rows.sort(key=lambda g: -abs(g.gbi_vs_baseline))
    ref = sum(g.referred for g in r.gatekeeping)
    rep = sum(g.reported for g in r.gatekeeping)
    worst = min(rows, key=lambda g: g.reported / g.referred)
    ex = next(g for g in rows if g.gbi_vs_baseline > 0)   # the worked example

    def lean(v):
        return (f"+{v:.1f} conservative" if v > 0 else f"&minus;{abs(v):.1f} liberal")

    worked = (
        '  <div class="tw"><table class="calc">\n'
        f'    <tr><td>{COMMITTEE_NAMES[ex.code]}: bills by conservative-record sponsors sent forward</td>'
        f'<td class="n">{ex.con_reported} of {ex.con_referred} = {ex.survival_conservative:.1f}%</td></tr>\n'
        f'    <tr><td>{COMMITTEE_NAMES[ex.code]}: bills by liberal-record sponsors sent forward</td>'
        f'<td class="n">{ex.lib_reported} of {ex.lib_referred} = {ex.survival_liberal:.1f}%</td></tr>\n'
        f'    <tr><td>Gap</td><td class="n">{_signed(ex.gbi, 1)} points</td></tr>\n'
        f'    <tr><td>Minus the Senate-wide baseline</td>'
        f'<td class="n">&minus;{r.gatekeeping_baseline:.1f} points</td></tr>\n'
        f'    <tr class="total"><td>Favours conservative-record sponsors beyond the baseline by</td>'
        f'<td class="n">{_signed(ex.gbi_vs_baseline, 1)} points</td></tr>\n'
        '  </table></div>')

    table = ('  <div class="tw"><table>\n'
             '    <tr><th>Committee</th><th class="n">Liberal-record sponsors: sent forward</th>'
             '<th class="n">Conservative-record sponsors: sent forward</th><th class="n">Beyond baseline</th></tr>\n'
             + "".join(
                 f'    <tr><td>{COMMITTEE_NAMES.get(g.code, g.code)}</td>'
                 f'<td class="n">{g.lib_reported} of {g.lib_referred} ({g.survival_liberal:.1f}%)</td>'
                 f'<td class="n">{g.con_reported} of {g.con_referred} ({g.survival_conservative:.1f}%)</td>'
                 f'<td class="n">{lean(g.gbi_vs_baseline)}</td></tr>\n'
                 for g in rows[:4])
             + '  </table></div>')

    d = date.today()

    def _bill(k):
        import re as _re
        m = _re.match(r"^([A-Z]+)(\d+)$", k)
        names = {"HR": "H.R.", "S": "S.", "HJRES": "H.J.Res.", "SJRES": "S.J.Res.",
                 "HCONRES": "H.Con.Res.", "SCONRES": "S.Con.Res."}
        return f"{names.get(m.group(1), m.group(1))} {m.group(2)}" if m else k

    dem_m = st.median([v for b, v in r.scores.items() if r.senators[b].party == "Democrat"])
    rep_m = st.median([v for b, v in r.scores.items() if r.senators[b].party == "Republican"])
    anchor_table = ('  <div class="tw"><table>\n'
                    '    <tr><th>Landmark</th><th class="n">Position</th></tr>\n'
                    + "".join(f'    <tr><td>{r.senators[b].name}</td><td class="n">{_p100(r.scores[b], 0)}</td></tr>\n'
                              for b in ANCHOR_NAMES if b in r.scores)
                    + f'    <tr><td>Middle Democrat</td><td class="n">{_p100(dem_m, 0)}</td></tr>\n'
                    + f'    <tr><td>Middle Republican</td><td class="n">{_p100(rep_m, 0)}</td></tr>\n'
                    + '  </table></div>')

    oi = [o for o in r.output_ideology if o.is_reportable]
    oi_table = ('  <div class="tw"><table>\n'
                '    <tr><th>Committee</th><th class="n">Floor votes on its bills</th>'
                '<th class="n">Where they divided the Senate</th><th class="n">vs. Senate middle</th></tr>\n'
                + "".join(f'    <tr><td>{COMMITTEE_NAMES.get(o.code, o.code)}</td><td class="n">{o.n_votes}</td>'
                          f'<td class="n">{_p100(o.coi)}</td><td class="n">{_sd100(o.vs_senate)}</td></tr>\n'
                          for o in oi)
                + '  </table></div>')

    cm = sorted(r.committees, key=lambda c: -abs(c.median - r.chamber.median))[:6]
    cnd_table = ('  <div class="tw"><table>\n'
                 '    <tr><th>Committee</th><th class="n">Members\' midpoint</th><th class="n">vs. Senate middle</th>'
                 '<th class="n">Moves if one member changes</th></tr>\n'
                 + "".join(f'    <tr><td>{COMMITTEE_NAMES.get(c.code, c.code)}</td><td class="n">{_p100(c.median)}</td>'
                           f'<td class="n">{_sd100(c.median - r.chamber.median)}</td>'
                           f'<td class="n">{_d100(c.stability.worst_shift)}</td></tr>\n' for c in cm)
                 + '  </table></div>')
    return {
        "asof": f"{d.day} {d.strftime('%B %Y')}",
        "os_x": _p100(os_.senator_coord), "os_s": _p100(os_.state_coord),
        "os_x_raw": _signed(os_.senator_coord), "os_s_raw": _signed(os_.state_coord),
        "os_se_raw": f"{r.state_source.state_se(os_.state) or 0:.3f}",
        "os_se": _d100(r.state_source.state_se(os_.state) or 0, 0),
        "os_vs_senate": _sd100(os_.senator_coord - r.chamber.median),
        "os_vs_senate_words": ("more liberal than" if os_.senator_coord < r.chamber.median else "more conservative than")
                              + " the Senate middle",
        "ga_vs_us": _sd100(os_.state_coord - r.chamber.national_coord) if r.chamber.national_coord is not None else "&mdash;",
        "ga_words": ("slightly conservative" if 0.05 < os_.state_coord <= 0.15 else "clearly conservative" if os_.state_coord > 0.15
                     else "slightly liberal" if -0.15 <= os_.state_coord < -0.05 else "clearly liberal" if os_.state_coord < -0.15
                     else "about in the middle"),
        "ch_m": _p100(r.chamber.median),
        "us_m": _p100(r.chamber.national_coord),
        "gk_referrals": f"{ref:,}",
        "gk_referred": f"{r.bills_referred_unique:,}", "gk_reported": str(r.bills_reported_unique),
        "gk_pct": str(round(100 * r.bills_reported_unique / r.bills_referred_unique)) if r.bills_referred_unique else "0",
        "gk_worst_name": COMMITTEE_NAMES.get(worst.code, worst.code),
        "gk_worst_rep": str(worst.reported), "gk_worst_ref": str(worst.referred),
        "gk_base": f"{r.gatekeeping_baseline:.1f}",
        "gk_n_reportable": NUMBER_WORDS[len(rows)] if len(rows) < len(NUMBER_WORDS) else str(len(rows)),
        "gk_asof": _billflow_asof(r.config) or "the last data refresh",
        "gk_worked": worked, "gk_table": table,
        "dem_m": _p100(dem_m, 0), "rep_m": _p100(rep_m, 0), "anchor_table": anchor_table,
        "os_votes": str(r.votes_cast.get("O000174", 0)),
        "oi_table": oi_table, "oi_count": str(len(oi)),
        "cnd_table": cnd_table,
        "pivot": _p100(r.chamber.pivot),
    }


def build_report(r: Report) -> bool:
    """Render methodology.html from its template. Returns True if it changed."""
    if not REPORT_TEMPLATE.exists():
        return False
    text = REPORT_TEMPLATE.read_text()
    for key, value in _report_values(r).items():
        text = text.replace("{{" + key + "}}", value)
    left = re.findall(r"\{\{(\w+)\}\}", text)
    if left:
        raise ValueError(f"unfilled placeholders in the report: {sorted(set(left))}")
    changed = not REPORT.exists() or REPORT.read_text() != text
    REPORT.write_text(text)
    return changed

STATES = {
 "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California",
 "CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia",
 "HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas",
 "KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland","MA":"Massachusetts",
 "MI":"Michigan","MN":"Minnesota","MS":"Mississippi","MO":"Missouri","MT":"Montana",
 "NE":"Nebraska","NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico",
 "NY":"New York","NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma",
 "OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina",
 "SD":"South Dakota","TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont",
 "VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming"}

COMMITTEE_NAMES = {
    "SSAF":"Agriculture","SSAP":"Appropriations","SSAS":"Armed Services",
    "SSBK":"Banking","SSBU":"Budget","SSCM":"Commerce","SSEG":"Energy",
    "SSEV":"Environment","SSFI":"Finance","SSFR":"Foreign Relations",
    "SSGA":"Homeland/Govt Affairs","SSHR":"HELP","SSJU":"Judiciary",
    "SSRA":"Rules","SSSB":"Small Business","SSVA":"Veterans",
    "SLET":"Ethics (select)","SLIN":"Intelligence (select)",
    "SLIA":"Indian Affairs (select)","SLAG":"Aging (select)",
}


# Familiar senators marked on the scale for perspective, most liberal to most
# conservative. Names as people know them; positions come from the data.
ANCHOR_NAMES = {
    "W000817": "Warren", "S000033": "Sanders", "S000148": "Schumer",
    "F000479": "Fetterman", "C001035": "Collins", "M000355": "McConnell",
    "T000250": "Thune", "C001098": "Cruz",
}
# The subset that fits on a senator card's track without crowding.
CARD_ANCHORS = {"S000033", "S000148", "C001035", "M000355", "C001098"}


def _blocks(r: Report, cfg: Config) -> dict[str, dict]:
    party = {b: s.party for b, s in r.senators.items()}
    by_state = defaultdict(list)
    for a in r.positions:
        if a.state_coord is not None:
            by_state[a.state].append(a)

    states = {}
    for stt, sens in by_state.items():
        sens.sort(key=lambda s: s.name.split()[-1])
        states[stt] = {
            "name": STATES.get(stt, stt),
            "center": round(sens[0].state_coord, 3),
            "se": round(r.state_source.state_se(stt) or 0, 3),
            "senators": [{
                "name": s.name, "party": party.get(s.bioguide, "?"),
                "bioguide": s.bioguide, "record": round(s.senator_coord, 3),
                "votes": r.votes_cast.get(s.bioguide),
            } for s in sens],
        }

    # senators held back by the vote threshold still get a card, marked as such
    for sen in r.unscored:
        entry = states.setdefault(sen.state, {
            "name": STATES.get(sen.state, sen.state), "center": 0.0,
            "se": 0.0, "senators": []})
        entry["senators"].append({
            "name": sen.name, "party": sen.party, "bioguide": sen.bioguide,
            "record": None, "votes": r.votes_cast.get(sen.bioguide),
        })

    scored = [a for a in r.positions if a.state_coord is not None]
    f = r.fit

    se_map = {}
    for a in scored:
        v = r.state_source.state_se(a.state)
        if v is not None:
            se_map[a.state] = round(v, 4)

    return {
        "V": {"states": states,
              "usM": round(r.chamber.national_coord, 3),
              "chM": round(r.chamber.median, 3),
              "congress": cfg.congress, "ideologyYear": cfg.ideology_year,
              "source": r.state_source.citation},
        "M": {"congress": cfg.congress, "scoreCol": cfg.score_column,
              "ideologyYear": cfg.ideology_year, "ideologyCol": "mrp_ideology",
              "se": se_map,
              "chM": round(r.chamber.median, 4),
              "usM": round(r.chamber.national_coord, 4),
              "popYear": cfg.population_year,
              "sources": [
                {"what": "Senator voting records", "who": "Voteview, University of California, Los Angeles",
                 "url": "https://voteview.com/data", "file": "https://voteview.com/static/data/out/members/HSall_members.csv",
                 "use": f"column {cfg.score_column}, rows for the {cfg.congress}th Congress, Senate",
                 "asof": _asof(cfg, "HSall_members.csv")},
                {"what": "Who currently holds each seat", "who": "congress-legislators, the @unitedstates project",
                 "url": "https://github.com/unitedstates/congress-legislators", "file": "https://unitedstates.github.io/congress-legislators/legislators-current.json",
                 "use": "joined on each member's Bioguide ID", "asof": _asof(cfg, "legislators-current.json")},
                {"what": "State voter estimates", "who": "American Ideology Project, Tausanovitch & Warshaw, Harvard Dataverse",
                 "url": "https://doi.org/10.7910/DVN/BQKU4M", "file": "https://dataverse.harvard.edu/api/access/datafile/6690212",
                 "use": f"file aip_states_ideology_v2022a.tab, column mrp_ideology and its standard error, {cfg.ideology_year} wave",
                 "asof": _asof(cfg, "aip_states_ideology_v2022a.tab")},
                {"what": "State populations", "who": "U.S. Census Bureau, population estimates",
                 "url": "https://www.census.gov/programs-surveys/popest.html",
                 "file": f"https://www2.census.gov/programs-surveys/popest/datasets/2020-{cfg.population_year}/state/totals/NST-EST{cfg.population_year}-ALLDATA.csv",
                 "use": f"column POPESTIMATE{cfg.population_year}, used to weight states", "asof": _asof(cfg, f"NST-EST{cfg.population_year}-ALLDATA.csv")},
                {"what": "Floor votes", "who": "Voteview, University of California, Los Angeles",
                 "url": "https://voteview.com/data", "file": f"https://voteview.com/static/data/out/rollcalls/S{cfg.congress}_rollcalls.csv",
                 "use": f"each roll call's dividing line (nominate_mid_1) and, in S{cfg.congress}_votes.csv, each senator's vote",
                 "asof": _asof(cfg, f"S{cfg.congress}_rollcalls.csv")},
                {"what": "Bills and committee actions", "who": "GovInfo bulk data, U.S. Government Publishing Office",
                 "url": f"https://www.govinfo.gov/bulkdata/BILLSTATUS/{cfg.congress}", "file": f"https://www.govinfo.gov/bulkdata/BILLSTATUS/{cfg.congress}/s/BILLSTATUS-{cfg.congress}-s.zip",
                 "use": "each bill's sponsor, the committees it was referred to, and whether each formally reported it",
                 "asof": _asof(cfg, f"BILLSTATUS-{cfg.congress}-s.zip")},
                {"what": "Committee rosters", "who": "congress-legislators, the @unitedstates project",
                 "url": "https://github.com/unitedstates/congress-legislators", "file": "https://unitedstates.github.io/congress-legislators/committee-membership-current.json",
                 "use": "current membership of each Senate committee", "asof": _asof(cfg, "committee-membership-current.json")},
              ]},
        "X": {"anchors": [
                  {"name": ANCHOR_NAMES[b], "full": r.senators[b].name,
                   "x": round(r.scores[b], 3), "card": b in CARD_ANCHORS}
                  for b in ANCHOR_NAMES if b in r.scores],
              "demMedian": round(st.median([v for b, v in r.scores.items()
                                            if r.senators[b].party == "Democrat"]), 3),
              "repMedian": round(st.median([v for b, v in r.scores.items()
                                            if r.senators[b].party == "Republican"]), 3),
              "chMedian": round(r.chamber.median, 3),
              "chMean": round(r.committees[0].chamber_mean, 3) if r.committees else 0.0,
              "output": {o.code: {"coi": round(o.coi, 3), "n": o.n_votes,
                                  "vsSen": round(o.vs_senate, 3)}
                         for o in r.output_ideology if o.is_reportable},
              "committees": sorted([
                  {"code": c.code, "name": COMMITTEE_NAMES.get(c.code, c.code),
                   "median": round(c.median, 3),
                   "drift": round(c.median - r.chamber.median, 3),
                   "mean": round(c.mean, 3), "meanDrift": round(c.ccd_mean, 3),
                   "shift": round(c.stability.worst_shift, 3),
                   "meanShift": round(c.mean_jackknife, 3),
                   "split": [c.n_majority, c.n_minority], "n": c.n_scored}
                  for c in r.committees],
                  key=lambda d: -abs(d["drift"])),
              "popSource": getattr(r.state_source, "population_source", ""),
              "popYear": cfg.population_year},
        "G": _gatekeeping_block(r, cfg),
        "P": _public_block(r, cfg),
    }


def _public_block(r: Report, cfg: Config) -> dict:
    """The Senate's own figures and every senator as one dot, plus the voter
    estimates on their own scale. Nothing here compares the two systems."""
    us = r.chamber.national_coord
    dots = []
    for a in r.positions:
        if a.state_coord is None:
            continue
        dots.append({
            "b": a.bioguide, "n": a.name, "st": a.state,
            "p": r.senators[a.bioguide].party[:1],
            "x": round(a.senator_coord, 3),
            "vsSen": round(a.senator_coord - r.chamber.median, 3),
        })
    dots.sort(key=lambda d: d["x"])
    # state voter estimates on their own scale, for the voter-side chart
    states = sorted({a.state for a in r.positions if a.state_coord is not None})
    return {
        "chM": round(r.chamber.median, 3),
        "usM": round(us, 3) if us is not None else None,
        "pivot": round(r.chamber.pivot, 3),
        "stateEstimates": [round(r.state_source.state(s), 3) for s in states
                           if r.state_source.state(s) is not None],
        "dots": dots,
    }


def _asof(cfg: Config, filename: str) -> str:
    """Date a raw file was last downloaded, from the provenance log (latest entry)."""
    prov = cfg.raw_dir / "PROVENANCE.tsv"
    if not prov.exists():
        return ""
    stamp = ""
    for line in prov.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1] == filename:
            stamp = parts[0]
    if not stamp:
        return ""
    from datetime import datetime
    d = datetime.strptime(stamp[:10], "%Y-%m-%d")
    return f"{d.day} {d.strftime('%B %Y')}"


def _billflow_asof(cfg: Config) -> str:
    return _asof(cfg, cfg.billflow_zip.name)


def _gatekeeping_block(r: Report, cfg: Config = DEFAULT) -> dict:
    """Pillar 6 by behaviour: which bills each committee has sent on so far.
    Every committee with referrals is listed with its counts; `ok` says whether
    both sides have at least 25 bills, the bar for comparing the two sides.
    totalReferred counts referrals (a bill sent to two committees counts twice);
    uniqueBills counts distinct bills."""
    rows = [g for g in r.gatekeeping if g.is_reportable]
    total_ref = sum(g.referred for g in r.gatekeeping)
    total_rep = sum(g.reported for g in r.gatekeeping)
    worst = min(rows, key=lambda g: g.reported / g.referred if g.referred else 1,
                default=None)
    return {
        "baseline": round(r.gatekeeping_baseline, 1),
        "totalReferred": total_ref,
        "totalReported": total_rep,
        "uniqueBills": r.bills_referred_unique,
        "uniqueReported": r.bills_reported_unique,
        "asOf": _billflow_asof(cfg),
        "worst": ({"name": COMMITTEE_NAMES.get(worst.code, worst.code),
                   "reported": worst.reported, "referred": worst.referred}
                  if worst else None),
        "committees": [
            {"code": g.code, "name": COMMITTEE_NAMES.get(g.code, g.code),
             "libRef": g.lib_referred, "libRep": g.lib_reported,
             "conRef": g.con_referred, "conRep": g.con_reported,
             "libPct": round(g.survival_liberal, 1),
             "conPct": round(g.survival_conservative, 1),
             "vsBase": round(g.gbi_vs_baseline, 1),
             "ok": g.is_reportable}
            for g in sorted(r.gatekeeping, key=lambda g: (-g.is_reportable, -abs(g.gbi_vs_baseline)))
            if g.referred > 0
        ],
    }


def build(cfg: Config = DEFAULT, path: Path = DEMO) -> dict[str, bool]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; nothing to rebuild")

    html = path.read_text()
    report = run(cfg)
    blocks = _blocks(report, cfg)
    changed = {}

    for key, value in blocks.items():
        literal = f"const {key}=" + json.dumps(value, separators=(",", ":")) + ";"
        pattern = re.compile(r"const " + key + r"=[\{\[].*?[\}\]];", re.S)
        if not pattern.search(html):
            raise ValueError(f"data block {key} not found in {path.name}")
        new_html = pattern.sub(lambda _m: literal, html, count=1)
        changed[key] = new_html != html
        html = new_html

    path.write_text(html)
    changed["report"] = build_report(report)
    return changed


def main() -> int:
    changed = build()
    moved = [k for k, v in changed.items() if v]
    print(f"rebuilt {DEMO.relative_to(DEMO.parents[1])}: "
          + (f"blocks changed: {', '.join(moved)}" if moved else "no figures moved"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
