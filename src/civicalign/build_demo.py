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


def _report_values(r: Report) -> dict[str, str]:
    from datetime import date

    scored = [a for a in r.alignments if a.abs_gap is not None]
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
        f'    <tr><td>{COMMITTEE_NAMES[ex.code]}: conservative bills through</td>'
        f'<td class="n">{ex.con_reported} of {ex.con_referred} = {ex.survival_conservative:.1f}%</td></tr>\n'
        f'    <tr><td>{COMMITTEE_NAMES[ex.code]}: liberal bills through</td>'
        f'<td class="n">{ex.lib_reported} of {ex.lib_referred} = {ex.survival_liberal:.1f}%</td></tr>\n'
        f'    <tr><td>Gap</td><td class="n">{_signed(ex.gbi, 1)} points</td></tr>\n'
        f'    <tr><td>Minus the Senate-wide baseline</td>'
        f'<td class="n">&minus;{r.gatekeeping_baseline:.1f} points</td></tr>\n'
        f'    <tr class="total"><td>Favours conservative bills beyond the baseline by</td>'
        f'<td class="n">{_signed(ex.gbi_vs_baseline, 1)} points</td></tr>\n'
        '  </table></div>')

    table = ('  <div class="tw"><table>\n'
             '    <tr><th>Committee</th><th class="n">Liberal bills through</th>'
             '<th class="n">Conservative bills through</th><th class="n">Beyond baseline</th></tr>\n'
             + "".join(
                 f'    <tr><td>{COMMITTEE_NAMES.get(g.code, g.code)}</td>'
                 f'<td class="n">{g.lib_reported} of {g.lib_referred} ({g.survival_liberal:.1f}%)</td>'
                 f'<td class="n">{g.con_reported} of {g.con_referred} ({g.survival_conservative:.1f}%)</td>'
                 f'<td class="n">{lean(g.gbi_vs_baseline)}</td></tr>\n'
                 for g in rows[:4])
             + '  </table></div>')

    top = ('  <div class="tw"><table>\n'
           '    <tr><th>Senator</th><th>State</th><th class="n">Record</th>'
           '<th class="n">Their state</th><th class="n">Gap</th><th class="n">Match</th></tr>\n'
           + "".join(
               f'    <tr><td>{a.name}</td><td>{a.state}</td>'
               f'<td class="n">{_signed(a.senator_coord)}</td>'
               f'<td class="n">{_signed(a.state_coord)}</td>'
               f'<td class="n">{a.abs_gap:.3f}</td><td class="n">{a.spec_score:.1f}%</td></tr>\n'
               for a in sorted(scored, key=lambda a: -a.abs_gap)[:5])
           + '  </table></div>')

    cross = sum(1 for a in scored if a.crosses_over)
    d = date.today()
    return {
        "asof": f"{d.day} {d.strftime('%B %Y')}",
        "os_x": _signed(os_.senator_coord), "os_s": _signed(os_.state_coord),
        "os_gap": f"{os_.abs_gap:.3f}", "os_as": f"{os_.spec_score:.1f}",
        "os_as_int": str(int(os_.spec_score)),
        "med_as": f"{st.median([a.spec_score for a in scored]):.1f}",
        "more_cons": str(sum(1 for a in scored if a.signed_gap > 0)),
        "more_lib": str(sum(1 for a in scored if a.signed_gap < 0)),
        "cross_word": NUMBER_WORDS[cross] if cross < len(NUMBER_WORDS) else str(cross),
        "top_table": top,
        "ch_m": _signed(r.chamber.median),
        "us_m": _signed(r.chamber.national_coord),
        "d_us": _signed(r.chamber.apportionment_skew),
        "gk_referred": f"{ref:,}", "gk_reported": str(rep),
        "gk_pct": str(round(100 * rep / ref)),
        "gk_worst_name": COMMITTEE_NAMES.get(worst.code, worst.code),
        "gk_worst_rep": str(worst.reported), "gk_worst_ref": str(worst.referred),
        "gk_base": f"{r.gatekeeping_baseline:.1f}",
        "gk_n_reportable": NUMBER_WORDS[len(rows)] if len(rows) < len(NUMBER_WORDS) else str(len(rows)),
        "gk_worked": worked, "gk_table": table,
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


def _blocks(r: Report, cfg: Config) -> dict[str, dict]:
    party = {b: s.party for b, s in r.senators.items()}
    by_state = defaultdict(list)
    for a in r.alignments:
        if a.abs_gap is not None:
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
                "gap": round(s.abs_gap, 3), "score": round(s.spec_score, 1),
                "rank": s.rank, "crosses": bool(s.crosses_over),
                "dir": "conservative" if s.signed_gap > 0 else "liberal",
            } for s in sens],
        }

    # senators held back by the vote threshold still get a card, marked as such
    for sen in r.unscored:
        entry = states.setdefault(sen.state, {
            "name": STATES.get(sen.state, sen.state), "center": 0.0,
            "se": 0.0, "senators": []})
        entry["senators"].append({
            "name": sen.name, "party": sen.party, "bioguide": sen.bioguide,
            "record": None, "gap": None, "score": None, "rank": None,
            "crosses": False, "dir": "",
        })

    scored = [a for a in r.alignments if a.abs_gap is not None]
    f = r.fit

    se_map = {}
    for a in scored:
        v = r.state_source.state_se(a.state)
        if v is not None:
            se_map[a.state] = round(v, 4)

    return {
        "V": {"states": states,
              "medianGap": round(st.median([a.abs_gap for a in scored]), 3),
              "usM": round(r.chamber.national_coord, 3),
              "chM": round(r.chamber.median, 3),
              "skew": round(r.chamber.apportionment_skew, 3),
              "congress": cfg.congress, "ideologyYear": cfg.ideology_year,
              "source": r.state_source.citation},
        "M": {"congress": cfg.congress, "scoreCol": cfg.score_column,
              "ideologyYear": cfg.ideology_year, "ideologyCol": "mrp_ideology",
              "se": se_map,
              "chM": round(r.chamber.median, 4),
              "usM": round(r.chamber.national_coord, 4),
              "dUS": round(r.chamber.apportionment_skew, 4),
              "popYear": cfg.population_year,
              "sources": [
                ["Senator positions",
                 "voteview.com/static/data/out/members/HSall_members.csv",
                 f"column {cfg.score_column}, rows where congress={cfg.congress} and chamber=Senate"],
                ["Who holds each seat",
                 "unitedstates.github.io/congress-legislators/legislators-current.json",
                 "joined on bioguide id"],
                ["State voter positions",
                 "dataverse.harvard.edu doi:10.7910/DVN/BQKU4M",
                 f"file aip_states_ideology_v2022a.tab, column mrp_ideology, {cfg.ideology_year} wave"],
                ["State populations",
                 "www2.census.gov/programs-surveys/popest/datasets/2020-2024/state/totals/",
                 f"NST-EST{cfg.population_year}-ALLDATA.csv, used to weight states"],
              ]},
        "X": {"anchors": [
                  {"name": r.senators[b].name.split()[-1],
                   "full": r.senators[b].name, "x": round(r.scores[b], 3)}
                  for b in ("S000033", "C001035", "C001098") if b in r.scores],
              "chMedian": round(r.chamber.median, 3),
              "chMean": round(r.committees[0].chamber_mean, 3) if r.committees else 0.0,
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
        "G": _gatekeeping_block(r),
        "C": {"medianScore": round(st.median([a.spec_score for a in scored]), 1),
              "medianGap": round(st.median([a.abs_gap for a in scored]), 3),
              "crossCount": sum(1 for a in scored if a.crosses_over),
              "moreCons": sum(1 for a in scored if a.signed_gap > 0),
              "moreLib": sum(1 for a in scored if a.signed_gap < 0)},
    }


def _gatekeeping_block(r: Report) -> dict:
    """Pillar 6 by behaviour: which bills each committee let through."""
    rows = [g for g in r.gatekeeping if g.is_reportable]
    total_ref = sum(g.referred for g in r.gatekeeping)
    total_rep = sum(g.reported for g in r.gatekeeping)
    worst = min(rows, key=lambda g: g.reported / g.referred if g.referred else 1,
                default=None)
    return {
        "baseline": round(r.gatekeeping_baseline, 1),
        "totalReferred": total_ref,
        "totalReported": total_rep,
        "worst": ({"name": COMMITTEE_NAMES.get(worst.code, worst.code),
                   "reported": worst.reported, "referred": worst.referred}
                  if worst else None),
        "committees": [
            {"code": g.code, "name": COMMITTEE_NAMES.get(g.code, g.code),
             "libRef": g.lib_referred, "libRep": g.lib_reported,
             "conRef": g.con_referred, "conRep": g.con_reported,
             "libPct": round(g.survival_liberal, 1),
             "conPct": round(g.survival_conservative, 1),
             "gap": round(g.gbi, 1), "vsBase": round(g.gbi_vs_baseline, 1)}
            for g in sorted(rows, key=lambda g: -abs(g.gbi_vs_baseline))
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
        pattern = re.compile(r"const " + key + r"=\{.*?\};", re.S)
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
