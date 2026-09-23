"""The supervisor: an independent recount of every headline figure before publishing.

WHY THIS EXISTS
---------------
The pipeline reads the raw files with one set of code and the tests mostly check
that the pages agree with the pipeline. If the pipeline itself misreads a file,
both agree and both are wrong. This module reads the same raw files with its own,
deliberately separate code, recomputes each published figure from scratch, and
compares. Any disagreement fails the update, so nothing is published.

It checks, from the raw files:
  * the roster (100 seated senators) and which of them carry a score
  * every senator's score, the Senate's middle and the 60th vote
  * every state's survey estimate and its standard error
  * the national public figure (population-weighted) and the Senate-public gap
  * every committee's bills-sent-on counts, the baseline, and the distinct-bill totals
and, once the page is built, that the page's data blocks say the same.

Run:  PYTHONPATH=src python -m civicalign.agents.supervisor
Exit 0 means every figure was independently confirmed.
"""
import csv
import io
import json
import re
import statistics
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ..config import DEFAULT, Config
from ..pipeline import Report, run

TOL = 1e-6


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""

    def line(self) -> str:
        return f"  {'ok  ' if self.ok else 'FAIL'}  {self.name:46s} {self.detail}"


# ---- independent readers -------------------------------------------------------

def _roster(cfg: Config) -> dict[str, dict]:
    people = json.loads(cfg.roster_json.read_text())
    out = {}
    for p in people:
        term = p["terms"][-1]
        if term["type"] == "sen":
            out[p["id"]["bioguide"]] = {"state": term["state"], "party": term.get("party", "")}
    return out


def _scores(cfg: Config, roster: dict) -> dict[str, float]:
    out = {}
    with cfg.members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["chamber"] != "Senate" or row["congress"] != str(cfg.congress):
                continue
            b = row["bioguide_id"]
            if b not in roster:
                continue
            try:
                cast = int(row.get("nominate_number_of_votes") or 0)
            except ValueError:
                cast = 0
            if cast < cfg.min_roll_calls or row.get(cfg.score_column, "") in ("", None):
                continue
            out[b] = float(row[cfg.score_column])
    return out


def _states(cfg: Config) -> dict[str, tuple[float, float]]:
    out = {}
    with cfg.ideology_tab.open() as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if int(row["presidential_year"]) == cfg.ideology_year:
                out[row["abb"].strip().strip('"')] = (float(row["mrp_ideology"]), float(row["mrp_ideology_se"]))
    return out


def _populations(cfg: Config) -> dict[str, int]:
    from ..build_demo import STATES
    name_to_usps = {v: k for k, v in STATES.items()}
    name_to_usps["District of Columbia"] = "DC"
    col = f"POPESTIMATE{cfg.population_year}"
    out = {}
    with cfg.population_csv.open(encoding="latin-1") as fh:
        for row in csv.DictReader(fh):
            if row.get("SUMLEV") == "040" and row["NAME"] in name_to_usps:
                out[name_to_usps[row["NAME"]]] = int(row[col])
    return out


def _gatekeeping(cfg: Config, scores: dict[str, float]) -> dict:
    per: dict[str, dict] = {}
    bills, reported = set(), set()
    referrals = 0
    with zipfile.ZipFile(cfg.billflow_zip) as z:
        for name in z.namelist():
            if not name.endswith(".xml"):
                continue
            try:
                bill = ET.parse(io.BytesIO(z.read(name))).getroot().find("bill")
            except ET.ParseError:
                continue
            if bill is None:
                continue
            sp = bill.find("sponsors/item")
            b = sp.findtext("bioguideId") if sp is not None else None
            if not b or b not in scores:
                continue
            label = f"{bill.findtext('type')} {bill.findtext('number')}"
            side = "lib" if scores[b] < 0 else "con"
            for c in bill.findall("committees/item"):
                code = (c.findtext("systemCode") or "")[:4].upper()
                if not code.startswith("S"):
                    continue
                acts = [a.findtext("name") or "" for a in c.findall("activities/item")]
                rep = any("Reported" in a for a in acts)
                d = per.setdefault(code, {"lib_r": 0, "lib_p": 0, "con_r": 0, "con_p": 0})
                d[side + "_r"] += 1
                referrals += 1
                bills.add(label)
                if rep:
                    d[side + "_p"] += 1
                    reported.add(label)
    tot = {k: sum(d[k] for d in per.values()) for k in ("lib_r", "lib_p", "con_r", "con_p")}
    base = (100 * tot["con_p"] / tot["con_r"] if tot["con_r"] else 0.0) - \
           (100 * tot["lib_p"] / tot["lib_r"] if tot["lib_r"] else 0.0)
    return {"per": per, "baseline": base, "referrals": referrals,
            "bills": len(bills), "reported": len(reported)}


# ---- the comparison ------------------------------------------------------------

def checks(report: Report, cfg: Config = DEFAULT, page: Path | None = None) -> list[Check]:
    out: list[Check] = []
    roster = _roster(cfg)
    out.append(Check("roster has 100 seated senators", len(roster) == 100, f"{len(roster)} found"))

    scores = _scores(cfg, roster)
    same = set(scores) == set(report.scores) and all(abs(scores[b] - report.scores[b]) < TOL for b in scores)
    out.append(Check("every senator score re-read from Voteview", same,
                     f"{len(scores)} scored independently, {len(report.scores)} in the pipeline"))

    if scores:
        med = statistics.median(scores.values())
        out.append(Check("Senate's middle (median of 100)", abs(med - report.chamber.median) < TOL,
                         f"{med:+.4f} vs pipeline {report.chamber.median:+.4f}"))
        piv = sorted(scores.values())[59] if len(scores) >= 60 else None
        out.append(Check("60th vote from the left", piv is not None and abs(piv - report.chamber.pivot) < TOL,
                         f"{piv:+.4f} vs pipeline {report.chamber.pivot:+.4f}" if piv is not None else "fewer than 60 scored"))

    states = _states(cfg)
    bad = [a.state for a in report.alignments if a.abs_gap is not None
           and (a.state not in states or abs(states[a.state][0] - a.state_coord) > TOL
                or abs(states[a.state][1] - (report.state_source.state_se(a.state) or 0)) > TOL)]
    out.append(Check("every state estimate and its standard error", not bad, f"mismatches: {bad}" if bad else f"{len(states)} states read"))

    pops = _populations(cfg)
    if pops and report.chamber.national_coord is not None:
        keys = [k for k in states if k in pops]
        us = sum(states[k][0] * pops[k] for k in keys) / sum(pops[k] for k in keys)
        out.append(Check("national public (population-weighted, incl. DC)",
                         abs(us - report.chamber.national_coord) < TOL and len(keys) == 51,
                         f"{us:+.4f} over {len(keys)} areas vs pipeline {report.chamber.national_coord:+.4f}"))
        skew = report.chamber.median - us
        out.append(Check("Senate-public gap", abs(skew - report.chamber.apportionment_skew) < TOL,
                         f"{skew:+.4f} vs pipeline {report.chamber.apportionment_skew:+.4f}"))

    if cfg.billflow_zip.exists() and scores:
        g = _gatekeeping(cfg, scores)
        by = {x.code: x for x in report.gatekeeping}
        mism = []
        for code, d in g["per"].items():
            x = by.get(code)
            if x is None or (x.lib_referred, x.lib_reported, x.con_referred, x.con_reported) != (d["lib_r"], d["lib_p"], d["con_r"], d["con_p"]):
                mism.append(code)
        extra = [c for c in by if c not in g["per"]]
        out.append(Check("every committee's bills-sent-on counts", not mism and not extra,
                         f"{len(g['per'])} committees recounted" + (f"; mismatches {mism + extra}" if mism or extra else "")))
        out.append(Check("chamber-wide baseline", abs(g["baseline"] - report.gatekeeping_baseline) < 1e-9,
                         f"{g['baseline']:+.2f} vs pipeline {report.gatekeeping_baseline:+.2f}"))
        out.append(Check("distinct bills sent to a committee / sent on",
                         (g["bills"], g["reported"]) == (report.bills_referred_unique, report.bills_reported_unique),
                         f"{g['bills']} / {g['reported']} vs pipeline {report.bills_referred_unique} / {report.bills_reported_unique}"))
        referrals = sum(x.referred for x in report.gatekeeping)
        out.append(Check("referral rows", g["referrals"] == referrals, f"{g['referrals']} vs pipeline {referrals}"))

    if page is not None and page.exists():
        html = page.read_text()

        def block(k):
            m = re.search(r"const " + k + r"=(\{.*?\});", html, re.S)
            return json.loads(m.group(1)) if m else None

        M, V, P, G, X = block("M"), block("V"), block("P"), block("G"), block("X")
        if M and V and P and G and X:
            ok = abs(M["chM"] - report.chamber.median) < 1e-4 and abs(M["usM"] - report.chamber.national_coord) < 1e-4
            out.append(Check("page: Senate middle and public figures", ok, f"M.chM={M['chM']} M.usM={M['usM']}"))
            recs = {s["bioguide"]: s["record"] for st in V["states"].values() for s in st["senators"] if s["record"] is not None}
            ok = set(recs) == set(scores) and all(abs(recs[b] - scores[b]) < 1e-3 for b in recs)
            out.append(Check("page: every senator's position", ok, f"{len(recs)} senators on the page"))
            ok = all(abs(V["states"][k]["center"] - states[k][0]) < 1e-3 for k in V["states"] if V["states"][k]["se"] > 0)
            out.append(Check("page: every state's position", ok))
            ok = len(P["dots"]) == 100 and all(abs((P["chM"] + d["vsSen"]) - scores[d["b"]]) < 2e-3 for d in P["dots"])
            out.append(Check("page: 100 circles at the right positions", ok))
            forbidden = {"gap", "score", "rank", "crosses", "dir", "vsState", "vsUS", "nRightOfPublic",
                         "nLeftOfPublic", "medianGap", "skew", "dUS", "cndMedian", "cndMean", "crossCount", "moreCons", "moreLib"}
            def keys(o):
                if isinstance(o, dict):
                    for k, v in o.items():
                        yield k
                        yield from keys(v)
                elif isinstance(o, list):
                    for v in o:
                        yield from keys(v)
            found = sorted({k for blk in (M, V, P, G, X) for k in keys(blk) if k in forbidden})
            out.append(Check("page: no cross-scale derived fields in the public payload", not found, f"found {found}" if found else ""))
            ok = (G["uniqueBills"], G["uniqueReported"]) == (report.bills_referred_unique, report.bills_reported_unique)
            out.append(Check("page: distinct-bill totals", ok, f"{G['uniqueBills']} / {G['uniqueReported']}"))
            dem = statistics.median(v for b, v in scores.items() if roster[b]["party"] == "Democrat")
            rep = statistics.median(v for b, v in scores.items() if roster[b]["party"] == "Republican")
            ok = abs(X["demMedian"] - dem) < 1e-3 and abs(X["repMedian"] - rep) < 1e-3
            out.append(Check("page: party middles", ok, f"{X['demMedian']} / {X['repMedian']}"))
            ok = all(abs(a["x"] - scores[next(b for b in scores if b in roster and _name_matches(a, b, cfg))]) < 1e-3 for a in X["anchors"]) if X["anchors"] else False
            out.append(Check("page: familiar senators at their real positions", ok, f"{len(X['anchors'])} anchors"))
        else:
            out.append(Check("page data blocks present", False, "a block is missing from the page"))
    return out


def _name_matches(anchor: dict, bioguide: str, cfg: Config) -> bool:
    from ..build_demo import ANCHOR_NAMES
    return ANCHOR_NAMES.get(bioguide) == anchor["name"]


def main() -> int:
    cfg = DEFAULT
    print("Supervisor: independent recount of every published figure\n")
    report = run(cfg)
    page = Path(__file__).resolve().parents[3] / "demo" / "senator-check.html"
    results = checks(report, cfg, page)
    for c in results:
        print(c.line())
    failed = [c for c in results if not c.ok]
    print()
    if failed:
        print(f"  {len(failed)} figure(s) could not be confirmed. Nothing should be published until this is resolved.")
        return 1
    print(f"  all {len(results)} checks confirmed independently.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
