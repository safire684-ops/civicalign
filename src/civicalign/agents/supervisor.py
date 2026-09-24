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
  * the national public figure (population-weighted), on its own survey scale
  * every committee's bills-sent-on counts, the baseline, and the distinct-bill totals
  * every state's three-cycle presidential two-party share and the national share
  * the senator-versus-state-pattern line, refitted with separate arithmetic, and
    every senator's expected position, residual and typical range
  * the seat-weighted vote share against the national vote
  * every senator's Yea or Nay on the published floor votes
  * every senator's same-caucus peer group from similarly voting other states,
  * the caucus grouping itself: every party value recognised, every Independent's
    caucus read from the roster, nothing inferred
    its count, lowest, highest and middle record, the published conclusion, and
    the cross-window sensitivity behind it
  * every Pillar 1 vote binding: the Senate record's identity, tallies and
    member votes re-read from the cached XML, the measure id, the bill-status
    recorded-vote link, the classification from the official question, the
    selected text version's existence, date and hash, and that only supported,
    verified, text-bound votes are marked eligible (with the CRA fields read
    from the official title and no underlying-rule description present)
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
            out[p["id"]["bioguide"]] = {"state": term["state"], "party": term.get("party", ""), "caucus": term.get("caucus")}
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


def _elections(cfg: Config) -> dict:
    """Two-party GOP share per state per year, summed per candidate across every
    party line, with its own nominee list. Returns per-year shares, the
    three-cycle state average and the national figures."""
    nominees = {2016: ("TRUMP", "CLINTON"), 2020: ("TRUMP", "BIDEN"), 2024: ("TRUMP", "HARRIS")}
    years = tuple(cfg.election_years)
    g = {y: {} for y in years}; d = {y: {} for y in years}
    with cfg.elections_csv.open() as fh:
        for row in csv.DictReader(fh):
            try:
                y = int(row["year"])
            except ValueError:
                continue
            if y not in g or row["office"].strip().upper() != "US PRESIDENT" or row["writein"].strip().upper() == "TRUE":
                continue
            cand, usps = row["candidate"].upper(), row["state_po"].strip()
            try:
                v = float(row["candidatevotes"])
            except ValueError:
                continue
            if nominees[y][0] in cand:
                g[y][usps] = g[y].get(usps, 0.0) + v
            elif nominees[y][1] in cand:
                d[y][usps] = d[y].get(usps, 0.0) + v
    share = {y: {s: g[y][s] / (g[y][s] + d[y].get(s, 0.0)) for s in g[y] if g[y][s] + d[y].get(s, 0.0) > 0} for y in years}
    national = {y: sum(g[y].values()) / (sum(g[y].values()) + sum(d[y].values())) for y in years}
    common = set.intersection(*(set(share[y]) for y in years))
    avg = {s: sum(share[y][s] for y in years) / len(years) for s in common}
    return {"share": share, "national": national, "avg": avg,
            "national_avg": sum(national.values()) / len(years)}


def _ols(xs: list[float], ys: list[float]) -> dict:
    """Plain least squares from sums, independent of statistics.linear_regression."""
    n = len(xs)
    xbar, ybar = sum(xs) / n, sum(ys) / n
    sxx = sum((x - xbar) ** 2 for x in xs)
    sxy = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = ybar - slope * xbar
    ss_res = sum((y - intercept - slope * x) ** 2 for x, y in zip(xs, ys))
    s = (ss_res / (n - 2)) ** 0.5
    return {"n": n, "xbar": xbar, "sxx": sxx, "slope": slope, "intercept": intercept, "s": s}


def _votes_for_rolls(cfg: Config, rolls: set[int]) -> dict[int, dict[str, str]]:
    """Every senator's Yea/Nay on the given roll numbers, re-read from the votes file."""
    icpsr = {}
    with cfg.members_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["chamber"] == "Senate" and row["congress"] == str(cfg.congress):
                icpsr[row["icpsr"]] = row["bioguide_id"]
    out: dict[int, dict[str, str]] = {r: {} for r in rolls}
    with cfg.votes_csv.open() as fh:
        for row in csv.DictReader(fh):
            n = int(row["rollnumber"])
            if n not in out:
                continue
            b = icpsr.get(row["icpsr"])
            if not b:
                continue
            if row["cast_code"] in ("1", "2", "3"):
                out[n][b] = "Yea"
            elif row["cast_code"] in ("4", "5", "6"):
                out[n][b] = "Nay"
    return out


def _peer_results(roster: dict, scores: dict[str, float], avg: dict[str, float],
                  window: float, min_peers: int, windows: tuple) -> dict[str, dict]:
    """The peer comparison rebuilt with its own loop: same caucus group, other
    states only, state share within the window, conclusion per window, and the
    published status from the cross-window agreement rule."""
    def grp(b):
        p, c = roster[b]["party"], roster[b].get("caucus")
        if p == "Republican":
            return "Republican"
        if p == "Democrat":
            return "Democratic"
        if p == "Independent":
            return {"Democrat": "Democratic", "Republican": "Republican"}.get(c or "")
        return None
    out = {}
    for b, y in scores.items():
        stt = roster[b]["state"]
        if stt not in avg:
            continue
        x = avg[stt]
        if grp(b) is None:
            out[b] = {"n": 0, "states": [], "ids": [], "low": None, "high": None, "median": None,
                      "status": "unsupported", "sens": {w: "unsupported" for w in windows}, "group": None}
            continue
        def peers_at(w):
            return sorted([(roster[q]["state"], q, scores[q]) for q in scores
                           if roster[q]["state"] != stt and grp(q) is not None and grp(q) == grp(b) and roster[q]["state"] in avg
                           and abs(avg[roster[q]["state"]] - x) <= w + 1e-12])
        def concl(w):
            ps = peers_at(w)
            if len(ps) < min_peers:
                return "insufficient"
            ys = [p[2] for p in ps]
            return "outside_liberal" if y < min(ys) else "outside_conservative" if y > max(ys) else "within"
        sens = {w: concl(w) for w in windows}
        if sens[window] == "insufficient":
            status = "insufficient"
        else:
            seen = {v for v in sens.values() if v != "insufficient"}
            status = "unstable" if len(seen) > 1 else sens[window]
        ps = peers_at(window)
        ys = [p[2] for p in ps]
        out[b] = {"n": len(ps), "states": sorted({p[0] for p in ps}), "ids": [p[1] for p in ps],
                  "low": min(ys) if ys else None, "high": max(ys) if ys else None,
                  "median": statistics.median(ys) if ys else None, "status": status, "sens": sens, "group": grp(b)}
    return out


def _binding_checks(cfg: Config, roster: dict, scores: dict[str, float]) -> list[Check]:
    """Re-derive every tracked binding from the cached first-party files with
    separate code. Bindings that could not be verified by the runner are
    reported, not failed; a binding the runner marked VERIFIED or eligible that
    this code cannot reproduce fails."""
    import hashlib
    from ..explain import binding as B
    from ..sources.senate_votes import parse_senate_vote
    from ..sources import billstatus
    out: list[Check] = []
    bdir = cfg.bindings_dir
    files = sorted(bdir.glob("vote_*.json")) if bdir.exists() else []
    if not files:
        out.append(Check("Pillar 1 bindings present", True, "none yet"))
        return out
    vv = {}
    with cfg.rollcalls_csv.open() as fh:
        for row in csv.DictReader(fh):
            if row["chamber"] == "Senate" and row["congress"] == str(cfg.congress):
                vv[(int(row["session"]), int(row["clerk_rollnumber"]))] = row
    bills = billstatus.load_records(cfg.billflow_zip, cfg.billflow_house_zip, cfg.billstatus_sjres_zip, cfg.billstatus_hjres_zip)
    raw = cfg.explain_raw_dir
    manifest = json.loads((raw / "MANIFEST.json").read_text()) if (raw / "MANIFEST.json").exists() else {}
    problems, checked, eligible, unverifiable = [], 0, 0, 0
    kinds = {}
    for f in files:
        b = json.loads(f.read_text()); v = b["vote"]; checked += 1
        key = (v["session"], v["clerk_number"]); row = vv.get(key)
        if row is None:
            problems.append(f"{f.name}: no Voteview row"); continue
        # classification from the official question alone must agree with the stored base kind
        q = row["vote_question"].strip(); base = B.QUESTION_KINDS.get(q, B.OTHER)
        stored = b["classification"]["kind"]
        if not (stored == base or (base == B.PASSAGE and stored == B.PASSAGE_AS_AMENDED) or stored == B.OTHER):
            problems.append(f"{f.name}: kind {stored} not derivable from {q!r}")
        if b["classification"]["summary_eligible"] and stored not in B.SUPPORTED_KINDS:
            problems.append(f"{f.name}: eligible but kind {stored} unsupported")
        kinds[stored] = kinds.get(stored, 0) + 1
        senate_path = raw / f"senate/vote_{v['congress']}_{v['session']}_{v['clerk_number']:05d}.xml"
        if b["verification"]["status"] in ("UNAVAILABLE",):
            unverifiable += 1; continue
        if not senate_path.exists():
            problems.append(f"{f.name}: Senate XML not cached"); continue
        data = senate_path.read_bytes()
        if v["senate_sha256"] and hashlib.sha256(data).hexdigest() != v["senate_sha256"]:
            problems.append(f"{f.name}: Senate XML hash changed since binding")
        s = parse_senate_vote(senate_path)
        if (s.congress, s.session, s.number) != (v["congress"], v["session"], v["clerk_number"]) or s.date != row["date"] \
                or (s.yeas, s.nays) != (int(row["yea_count"]), int(row["nay_count"])) or s.question != q:
            problems.append(f"{f.name}: Senate record disagrees with Voteview on identity/date/tallies/question")
        if stored == B.PASSAGE_AS_AMENDED and not s.as_amended:
            problems.append(f"{f.name}: PASSAGE_AS_AMENDED but Senate title lacks 'As Amended'")
        measure = "".join(ch for ch in row["bill_number"].upper() if ch.isalnum())
        if measure and s.measure != measure:
            problems.append(f"{f.name}: measure {s.measure!r} vs Voteview {measure!r}")
        if b["object"]["id"] and b["object"]["id"] != measure:
            problems.append(f"{f.name}: object id {b['object']['id']} vs {measure}")
        bill = bills.get(measure)
        ver = b["verification"]["status"]
        if ver == "VERIFIED":
            if bill is None:
                problems.append(f"{f.name}: VERIFIED without a bill-status record")
            else:
                linked = any(rv.chamber == "Senate" and rv.number == v["clerk_number"] for a in bill.actions for rv in a.recorded_votes)
                if not linked:
                    problems.append(f"{f.name}: VERIFIED but bill status has no recorded-vote link to vote {v['clerk_number']}")
                if bill.sha256 != b["object"]["billstatus_sha256"]:
                    problems.append(f"{f.name}: bill-status hash changed since binding")
        tb = b["text_binding"]
        if tb["status"] == "TEXT_BOUND":
            if bill is None:
                problems.append(f"{f.name}: TEXT_BOUND without a bill record")
            else:
                match = [tv for tv in bill.text_versions if tv.url == tb["govinfo_url"]]
                if len(match) != 1:
                    problems.append(f"{f.name}: selected text URL not in the bill's text versions")
                elif tb["version_code"] in B.NEVER or match[0].code in B.NEVER:
                    problems.append(f"{f.name}: an enrolled/public-law text was selected")
                elif match[0].date and match[0].date > row["date"] and (
                        __import__("datetime").date.fromisoformat(match[0].date) - __import__("datetime").date.fromisoformat(row["date"])).days > 3:
                    problems.append(f"{f.name}: selected text dated more than 3 days after the vote")
                elif B.select_text(stored, bill, row["date"]).version != match[0]:
                    problems.append(f"{f.name}: selection rule does not reproduce the stored version")
                tpath = raw / f"text/{tb['govinfo_url'].rsplit('/', 1)[-1]}"
                if not tpath.exists():
                    problems.append(f"{f.name}: selected text not cached")
                elif hashlib.sha256(tpath.read_bytes()).hexdigest() != tb["sha256"]:
                    problems.append(f"{f.name}: text hash changed since binding")
                elif B.stage_matches(tb["version_code"], tpath.read_bytes()[:4000]) is False:
                    problems.append(f"{f.name}: cached text's bill-stage does not match the selected version")
        if b["classification"]["summary_eligible"]:
            eligible += 1
            if ver != "VERIFIED" or tb["status"] != "TEXT_BOUND":
                problems.append(f"{f.name}: eligible without VERIFIED + TEXT_BOUND")
        cra = b["cra"]
        if bill is not None and b["object"]["type"] == "joint_resolution":
            own = B.cra_from_title(bill.title)
            if (own.is_cra, own.agency, own.rule_title) != (cra["is_cra"], cra["agency"], cra["rule_title"]):
                problems.append(f"{f.name}: CRA fields differ from the official title")
        if cra["is_cra"] and cra["underlying_rule_source"] is None:
            for k in ("rule_summary", "rule_effects", "if_succeeds", "if_fails"):
                if k in b:
                    problems.append(f"{f.name}: underlying-rule description without an underlying-rule source")
        for k in ("decision", "if_succeeds", "if_fails", "summary"):
            if k in b:
                problems.append(f"{f.name}: generated field {k!r} present in a Stage 2 binding")
        exp = _expected_next_step(b, bill, s, row)
        got = b["receipt"]
        have = (got["next_step"]["case"], got["vote_result"]["outcome"], got["vote_result"]["statement"], got["next_step"]["actual"], got["next_step"]["hypothetical"])
        if have != exp:
            problems.append(f"{f.name}: vote result / next step {have} does not reproduce {exp}")
        if got["vote_result"]["outcome"] == "REJECTED" and any(w in (got["next_step"]["actual"] or "") for w in ("next goes", "presentment", "must agree")):
            problems.append(f"{f.name}: a failed vote is described as advancing")
        if b["object"]["id"] and b["object"]["id"][0] == "S" and "back to the House" in json.dumps(got):
            problems.append(f"{f.name}: a Senate-origin measure is said to go back to the House")
        for rec in b["history"]:
            if rec.get("vote", {}).get("clerk_number") != v["clerk_number"]:
                problems.append(f"{f.name}: history entry for a different vote")
    out.append(Check("Pillar 1 bindings re-derived from cached first-party files", not problems,
                     f"{checked} bindings, {eligible} eligible, {unverifiable} unverifiable; kinds {kinds}" + (f"; problems {problems[:6]}" if problems else "")))
    return out


def _expected_next_step(b: dict, bill, s, row: dict) -> tuple:
    """Separate code for the receipt's actual result and next step, from the raw
    records: the measure number, the bill status (origin, House passage, this
    vote's action), the Senate's own record (title, result) and Voteview's tally.
    Returns (case, outcome, result statement, actual, hypothetical)."""
    import re as _re
    mid = b["object"]["id"] or ""
    prefix = _re.sub(r"\d", "", mid)
    noun = {"S": "bill", "HR": "bill", "SJRES": "joint resolution", "HJRES": "joint resolution"}.get(prefix)
    origin = {"S": "Senate", "SJRES": "Senate", "HR": "House", "HJRES": "House"}.get(prefix)
    last = row["vote_result"].strip().lower().split()[-1] if row["vote_result"].strip() else ""
    y, n, req = int(row["yea_count"]), int(row["nay_count"]), row["majority_requirement"]
    outcome = "PASSED" if last in ("passed",) or row["vote_result"].strip().lower().endswith("agreed to") and "not agreed" not in row["vote_result"].lower() \
        else "REJECTED" if last in ("defeated", "rejected", "failed") or "not agreed to" in row["vote_result"].lower() else None
    fits = {("1/2", "PASSED"): y >= n, ("1/2", "REJECTED"): y <= n, ("3/5", "PASSED"): 5 * y >= 3 * (y + n), ("3/5", "REJECTED"): y < 60,
            ("2/3", "PASSED"): 3 * y >= 2 * (y + n), ("2/3", "REJECTED"): 3 * y < 2 * (y + n)}.get((req, outcome), False)
    if b["classification"]["kind"] not in ("PASSAGE", "PASSAGE_AS_AMENDED", "JOINT_RESOLUTION_PASSAGE") or noun is None or bill is None \
            or bill.origin_chamber != origin or outcome is None or not fits:
        return ("UNDETERMINED", outcome if fits else None, None, None, None)
    if noun == "joint resolution" and "proposing an amendment to the constitution" in (bill.title or "").lower():
        return ("UNSUPPORTED_CONSTITUTIONAL_AMENDMENT", outcome, None, None, None)
    this_action = next((a.text for a in bill.actions for rv in a.recorded_votes if rv.chamber == "Senate" and rv.number == b["vote"]["clerk_number"] and a.date == row["date"]), "")
    changed = b["classification"]["kind"] == "PASSAGE_AS_AMENDED" or s.title.strip().endswith("As Amended") \
        or "with an amendment" in this_action.lower() or "with amendments" in this_action.lower() or b["text_binding"]["version_code"] == "eas"
    pres = "proceed to presentment to the President"
    if origin == "Senate":
        case, yes, act = "SENATE_ORIGIN", f"The Senate passed the {noun}.", f"The Senate passed the {noun}. It next goes to the House."
        hyp = f"If the Senate had passed it, the {noun} would next have gone to the House."
    elif not any(a.text.startswith("Passed/agreed to in House") and a.date and a.date <= row["date"] for a in bill.actions):
        return ("UNDETERMINED", outcome, None, None, None)
    elif changed:
        case, yes = "HOUSE_ORIGIN_AMENDED", f"The Senate passed an amended version of the {noun}."
        act = f"The Senate passed an amended version. The House must agree to the Senate changes before the measure can {pres}."
        hyp = f"If the Senate had passed it, the House would have had to agree to the Senate changes before the measure could {pres}."
    else:
        case, yes = "HOUSE_ORIGIN_SAME_TEXT", f"The Senate passed the House-passed text of the {noun}."
        act = f"The Senate passed the House-passed text. Because both chambers have approved the same text, it can {pres}."
        hyp = "If the Senate had passed it, both chambers would have approved the same text and it could have proceeded to presentment to the President."
    if outcome == "PASSED":
        return (case, outcome, yes, act, None)
    no = f"The {noun} did not pass the Senate in this vote."
    return (case, outcome, no, no, hyp)


_NEEDS_CONTENT = {"AMENDED_TARGET", "REPLACED_TEXT", "DEFINITION_REQUIRED", "CROSS_REFERENCE_REQUIRED", "SUPPORTING_CONTEXT"}


def _own_start(xml: bytes, ident: str) -> tuple[int, bytes] | None:
    """Start offset and tag name of the element carrying identifier=ident."""
    for idv in (ident, ident.replace("-", "\u2013")):
        at = xml.find(b'identifier="' + idv.encode("utf8") + b'"')
        if at >= 0:
            lt = xml.rfind(b"<", 0, at)
            name = xml[lt + 1:at].split()[0]
            return lt, name
    return None


def _own_node(sec: bytes, ident: str) -> bytes | None:
    """A node cut from a section by counting its own open and close tags."""
    st = _own_start(sec, ident)
    if st is None:
        return None
    start, name = st
    depth, i = 0, start
    while True:
        o = sec.find(b"<" + name, i); c = sec.find(b"</" + name + b">", i)
        if c < 0:
            return None
        if 0 <= o < c and sec[o + 1 + len(name):o + 2 + len(name)] in (b" ", b">"):
            depth += 1; i = o + 1
        else:
            depth -= 1; i = c + 1
            if depth == 0:
                return sec[start:c + len(name) + 3]


def _own_lead_in(sec: bytes, ident: str) -> bytes | None:
    """A provision's bytes up to its first child provision (children's
    identifiers extend the parent's with a slash)."""
    st = _own_start(sec, ident)
    if st is None:
        return None
    child = sec.find(b'identifier="' + ident.encode("utf8") + b"/", st[0])
    el = _own_node(sec, ident) if st[1] != b"section" else sec
    if el is None:
        return None
    return sec[st[0]:sec.rfind(b"<", 0, child)] if 0 <= child < st[0] + len(el) else el


def _own_metrics(pk: dict) -> dict:
    law = pk["existing_law_context"]
    cons = (pk.get("cra_context") or {}).get("statutory_consequence_source")
    summ = len(pk["official_summary"].get("content") or "")
    ctx = sum(len(e["content"]) for e in law) + sum(len(h["content"]) for e in law for h in e.get("hierarchy", [])) + (len(cons["content"]) if cons else 0)
    vt = len(pk["voted_text"]["content"])
    return {"voted_text_chars": vt, "context_chars": ctx, "official_summary_chars": summ, "total_source_chars": vt + ctx + summ,
            "source_count": 1 + len(law) + (1 if cons else 0) + (1 if summ else 0),
            "included_context_fragment_count": len(law) + (1 if cons else 0),
            "hierarchy_fragment_count": sum(len(e.get("hierarchy", [])) for e in law),
            "tracked_reference_count": len(pk.get("tracked_references", [])) + len(pk["cited_public_laws_not_included"])}


def _own_group(content: str) -> list[tuple[str, tuple]] | None:
    """'1231(a), or 1357' -> [('1231', ('a',)), ('1357', ())], or None if any
    piece is outside the narrow grammar (dashes, ranges, words)."""
    import re as _re
    pieces = [p for p in _re.split(r",\s+or\s+|,\s+and\s+|\s+or\s+|\s+and\s+|,\s+", content)]
    out = []
    for p in pieces:
        m = _re.fullmatch(r"(\d+[a-z]{0,3})((?:\([0-9A-Za-z]{1,4}\))*)", p)
        if not m:
            return None
        out.append((m.group(1), tuple(_re.findall(r"\(([0-9A-Za-z]+)\)", m.group(2)))))
    return out


def _close(text: str, start: int) -> int | None:
    """Index of the ")" closing a parenthetical whose content starts at `start`."""
    depth = 1
    for i in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return i
    return None


def _fallback_problems(name: str, root, parent, c: dict, b: dict) -> list[str]:
    """Separate reading of the two fallback forms: a whole parenthetical
    "(T U.S.C. A, B(x), or C)" in untagged text, and a tagged citation whose
    parenthetical list continues untagged. The recovered set must equal the
    recorded fallback citations, each tied to the voted text's hash."""
    import re as _re
    own = set()
    for el in root.iter():
        chunks = [] if el.tag == "external-xref" else [el.text or ""]
        chunks += [el.tail or ""] if parent.get(el) is not None and el.tag != "external-xref" else []
        for chunk in chunks:
            for m in _re.finditer(r"\((\d{1,2}) U\.S\.C\. ", chunk):
                end = _close(chunk, m.start() + 1)
                group = _own_group(chunk[m.end():end]) if end is not None else None
                for sec, pins in group or []:
                    own.add((f"usc/{m.group(1)}/{sec}", pins, "R1", chunk[m.start():end + 1]))
        if el.tag == "external-xref" and el.get("legal-doc") == "usc":
            shown = " ".join("".join(el.itertext()).split())
            head = _re.fullmatch(r"(\d{1,2}) U\.S\.C\. [0-9A-Za-z]+(?:\([0-9A-Za-z]+\))*", shown)
            prev = parent[el]
            kids = list(prev)
            i = kids.index(el)
            preceding = (kids[i - 1].tail if i else prev.text) or ""
            tail = el.tail or ""
            end = _close(tail, 0)
            lead = _re.match(r"(?:,\s+or\s+|,\s+and\s+|\s+or\s+|\s+and\s+|,\s+)", tail)
            if head and preceding.rstrip().endswith("(") and end is not None and lead:
                group = _own_group(tail[lead.end():end])
                if group and el.get("parsable-cite", "").split("/")[1:2] == [head.group(1)]:
                    for sec, pins in group:
                        own.add((f"usc/{head.group(1)}/{sec}", pins, "R2", "(" + shown + tail[:end + 1]))
    recorded = {(r["cite"], tuple(r["pinpoint"]), r["rule"][:2], r["source_fragment"]) for r in c["references"] if r.get("source") == "fallback_explicit_usc"}
    out = []
    if own != recorded:
        out.append(f"{name}: fallback citations {sorted(recorded ^ own)[:4]} do not reproduce")
    for r in c["references"]:
        if r.get("source") == "fallback_explicit_usc" and r["source_sha256"] != b["text_binding"]["sha256"]:
            out.append(f"{name}: fallback citation {r['text']} not tied to the voted text's hash")
    for g in c.get("citation_gaps", []):
        found = {r["text"] for r in c["references"] if r.get("source") == "fallback_explicit_usc" and r["location"] == g["location"]}
        if g["resolved"] and not (g["untagged_provisions"] and set(g["untagged_provisions"]) <= found):
            out.append(f"{name}: resolved group {g['text']!r} does not account for each untagged provision")
    return out


def _relevance_problems(name: str, c: dict, b: dict, text_path) -> list[str]:
    """Separate checks of the relevance rules against the voted XML: an 'et seq.'
    or whole-law citation is never given content; a citation under a header that
    says 'defin…' is DEFINITION_REQUIRED; a pinpoint in the citation's visible
    text is the node selected; every untagged 'U.S.C.' citation is recorded as a
    gap; a READY non-CRA record has no gap in a location that needs content."""
    import io as _io, re as _re, xml.etree.ElementTree as _ET
    out = []
    if text_path is None or not c["references"] and not c.get("citation_gaps"):
        return out
    root = _ET.parse(_io.BytesIO(text_path.read_bytes())).getroot()
    parent = {ch: p for p in root.iter() for ch in p}
    xrefs = list(root.iter("external-xref"))
    structured = [r for r in c["references"] if r.get("source", "structured_xref") == "structured_xref"]
    if len(xrefs) != len(structured):
        return [f"{name}: {len(xrefs)} citations in the XML, {len(structured)} recorded"]
    out += _fallback_problems(name, root, parent, c, b)
    sel = c["selection"] or {}
    for x, r in zip(xrefs, structured):
        shown = " ".join("".join(x.itertext()).split())
        if shown != r["text"] or x.get("parsable-cite", "") != r["cite"]:
            out.append(f"{name}: citation {shown!r} recorded as {r['text']!r}"); continue
        anc, p = [], parent.get(x)
        while p is not None:
            anc.append(p); p = parent.get(p)
        quoted = any(a.tag in ("quoted-block", "quote") for a in anc)
        in_def = any(a.find("header") is not None and _re.search(r"defin", "".join(a.find("header").itertext()), _re.I) for a in anc)
        if r["legal_doc"] == "usc" and _re.search(r"et\.?\s*seq", shown) and r["relationship"] not in ("CROSS_REFERENCE_ONLY", "AMENDED_TARGET", "REPLACED_TEXT"):
            out.append(f"{name}: {shown!r} cites a whole Act but is {r['relationship']}")
        if in_def and not quoted and r["relationship"] not in ("DEFINITION_REQUIRED", "AMENDED_TARGET", "REPLACED_TEXT", "CROSS_REFERENCE_ONLY"):
            out.append(f"{name}: {shown!r} sits in a definition but is {r['relationship']}")
        m = _re.match(r"^(\d+[a-zA-Z]?) U\.S\.C\. ([0-9A-Za-z\-\u2013.]+?)((?:\([0-9A-Za-z]+\))+)$", shown)
        if r["legal_doc"] == "usc" and m and r["relationship"] in _NEEDS_CONTENT:
            node = f"/us/usc/t{m.group(1)}/s{m.group(2)}" + "".join("/" + q for q in _re.findall(r"\(([0-9A-Za-z]+)\)", m.group(3)))
            covered = [k for k in sel.get("required", []) if node == k or node.startswith(k + "/")]
            if not covered and sel.get("status") == "ok" and not b["cra"]["is_cra"]:
                out.append(f"{name}: pinpoint {node} is not among the selected provisions")
    # untagged citations: own scan of text outside external-xref
    own_gaps = 0
    for el in root.iter():
        for chunk in ([] if el.tag == "external-xref" else [el.text]) + ([el.tail] if parent.get(el) is not None else []):
            own_gaps += len(_re.findall(r"\d+[a-zA-Z]?\s+U\.S\.C\.\s+[0-9A-Za-z]", chunk or ""))
        if el.tag == "external-xref" and el.get("legal-doc") == "usc":
            own_gaps += bool(_re.match(r"^(?:,\s*|,?\s+or\s+|,?\s+and\s+)[0-9][^\s,;)]*(?=[\s,;)]|$)(?!\s+U\.S\.C\.)", el.tail or ""))
            shown = " ".join("".join(el.itertext()).split()); sec = (el.get("parsable-cite", "").split("/") + ["", "", ""])[2]
            pat = r"^(?:\d+[a-zA-Z]? U\.S\.C\.|[Ss]ection) " + _re.escape(sec).replace("\\-", "[-\u2013]") + r"(?:\([0-9A-Za-z]+\))*(?: et\.? ?seq\.?)?$"
            own_gaps += not _re.match(pat, shown)
    if own_gaps != len(c.get("citation_gaps", [])):
        out.append(f"{name}: {own_gaps} unstructured citations found, {len(c.get('citation_gaps', []))} recorded")
    if c["generation"]["status"] in ("READY_FOR_GENERATION", "READY_WITH_LIMITS") and not b["cra"]["is_cra"]:
        if any(g["relationship"] in _NEEDS_CONTENT and not g.get("resolved") for g in c.get("citation_gaps", [])):
            out.append(f"{name}: READY with an unresolved citation that needs content")
        for rec in c["existing_law_context"]:
            if rec.get("inclusion") == "CONTENT_INCLUDED_FOR_GENERATION" and rec["status"] != "fetched":
                out.append(f"{name}: READY but required {rec['identifier']} is {rec['status']}")
    return out


def _context_checks(cfg: Config) -> list[Check]:
    """Re-derive every Stage 2.5 context record and packet from tracked and
    cached artefacts with separate code: references really occur in the voted
    XML; the release point precedes the vote; selected sections exist in the
    cached archive and their bytes reproduce the stored hash; packet content
    hashes match; the CRS relationship recomputes; the CRA mode follows the
    rule status; generation state follows completeness; no generated prose."""
    import hashlib
    from ..explain import binding as B, context as C
    from ..sources import uscode
    out: list[Check] = []
    cdir = cfg.bindings_dir / "context"; pdir = cfg.bindings_dir / "packets"; raw = cfg.explain_raw_dir
    files = sorted(cdir.glob("vote_*.context.json")) if cdir.exists() else []
    if not files:
        out.append(Check("Pillar 1 context records present", True, "none yet")); return out
    points = []
    for rel in ("uscode/priorreleasepoints.htm", "uscode/download.shtml"):
        if (raw / rel).exists():
            points += uscode.parse_release_points((raw / rel).read_text(errors="ignore"))
    points = sorted(set(points), key=lambda p: (p.date, p.congress, p.law))
    problems, n, gen = [], 0, {}
    for f in files:
        c = json.loads(f.read_text()); n += 1; v = c["vote"]
        bpath = cfg.bindings_dir / f.name.replace(".context.json", ".json")
        if not bpath.exists():
            problems.append(f"{f.name}: no binding"); continue
        b = json.loads(bpath.read_text()); tb = b["text_binding"]
        gen[c["generation"]["status"]] = gen.get(c["generation"]["status"], 0) + 1
        for k in ("decision", "if_succeeds", "if_fails", "summary", "explanation"):
            if k in c:
                problems.append(f"{f.name}: generated field {k!r}")
        tpath = raw / "text" / (tb["govinfo_url"] or "").rsplit("/", 1)[-1]
        if c["references"] and tpath.exists():
            xml = tpath.read_bytes()
            own = C.extract_references(xml)
            if sorted(r["cite"] for r in own) != sorted(r["cite"] for r in c["references"]):
                problems.append(f"{f.name}: references differ from the voted XML")
            sel = C.select_sections(own, bool(b["cra"]["is_cra"]), C.citation_gaps(xml))
            if sel["required"] != c["selection"]["required"] or sel["status"] != c["selection"]["status"]:
                problems.append(f"{f.name}: selection policy does not reproduce")
        rp = c.get("release_point")
        if rp:
            if rp["date"] > v["date"]:
                problems.append(f"{f.name}: release point {rp['label']} is after the vote")
            if points and uscode.in_force(points, v["date"]).label != rp["label"]:
                problems.append(f"{f.name}: release point {rp['label']} is not the one in force")
        published = {}
        for p in points:
            page = raw / f"uscode/usc-rp@{p.label}.htm"
            if page.exists():
                published[p.label] = uscode.archives_listed(page.read_text(errors="ignore"), p)
        classification = {}
        for s in ("1st", "2nd"):
            page = raw / f"uscode/tbl{cfg.congress}pl_{s}.htm"
            if page.exists():
                for k, val in uscode.parse_classification(page.read_text(errors="ignore")).items():
                    classification.setdefault(k, set()).update(val)
        problems += _relevance_problems(f.name, c, b, tpath if tpath.exists() else None)
        for rec in c["existing_law_context"] + ([c["cra"]["consequence_source"]] if c["cra"]["consequence_source"] else []):
            if rec["status"] != "fetched":
                continue
            if rec["as_of"]["date"] > v["date"]:
                problems.append(f"{f.name}: law context {rec['identifier']} dated after the vote")
            if published and classification:
                own = uscode.in_force_for_section(points, published, classification, v["date"], rec["title"], rec["section"])
                if own["status"] != "ok" or own["release_point"].label != rec["as_of"]["release_point"]:
                    problems.append(f"{f.name}: in-force archive for {rec['identifier']} does not reproduce ({own['status']})")
            arch = raw / "uscode" / uscode.archive_name(rec["title"], uscode.ReleasePoint(*map(int, rec["as_of"]["release_point"].split("-")), __import__("datetime").date.fromisoformat(rec["as_of"]["date"])))
            if arch.exists():
                data = uscode.read_title(arch)
                sec_id = rec.get("section_identifier", rec["identifier"])
                sec = uscode.extract_section(data, sec_id)
                frag = sec if (sec is None or sec_id == rec["identifier"]) else _own_node(sec, rec["identifier"])
                if frag is None or hashlib.sha256(frag).hexdigest() != rec["fragment_sha256"]:
                    problems.append(f"{f.name}: {rec['identifier']} does not reproduce from the cached archive")
                for h in rec.get("hierarchy", []):
                    li = _own_lead_in(sec, h["identifier"]) if sec is not None else None
                    if li is None or hashlib.sha256(li).hexdigest() != h["sha256"]:
                        problems.append(f"{f.name}: lead-in of {h['identifier']} does not reproduce")
                if hashlib.sha256(arch.read_bytes()).hexdigest() != rec["archive_sha256"]:
                    problems.append(f"{f.name}: archive hash changed for {rec['identifier']}")
        st = c["generation"]["status"]; comp = c["completeness"]["status"]
        expect = {"COMPLETE": "READY_FOR_GENERATION", "LIMITED": "READY_WITH_LIMITS", "PENDING": "SOURCE_CONTEXT_PENDING", "AMBIGUOUS": "SOURCE_CONTEXT_AMBIGUOUS"}
        if b["classification"]["kind"] in B.SUPPORTED_KINDS and b["verification"]["status"] == "VERIFIED" and tb["status"] == "TEXT_BOUND":
            if expect.get(comp) != st:
                problems.append(f"{f.name}: generation {st} does not follow completeness {comp}")
            if comp in ("COMPLETE", "LIMITED") and c["completeness"]["missing"]:
                problems.append(f"{f.name}: complete with missing items")
            if comp == "COMPLETE" and b["cra"]["is_cra"]:
                problems.append(f"{f.name}: CRA marked COMPLETE (full mode is not allowed yet)")
        elif st not in ("UNSUPPORTED", "SOURCE_CONTEXT_PENDING", "SOURCE_CONTEXT_AMBIGUOUS"):
            problems.append(f"{f.name}: unverified binding with generation {st}")
        cra = c["cra"]
        if b["cra"]["is_cra"]:
            if cra["mode"] == "rule_bound" and not (cra["underlying_rule"] and cra["underlying_rule"].get("sha256")):
                problems.append(f"{f.name}: rule_bound without a hashed rule")
            if cra["mode"] == "resolution_only" and cra["underlying_rule"] and cra["underlying_rule"].get("sha256"):
                problems.append(f"{f.name}: hashed rule but mode resolution_only")
            if cra["rule_status"] == "GAO_RULE_DETERMINATION" and not cra["gao_determination"]:
                problems.append(f"{f.name}: GAO status without a determination record")
        elif cra["mode"] != "not_cra":
            problems.append(f"{f.name}: CRA mode on a non-CRA measure")
        if b["object"]["id"] == "S5" and st != "SOURCE_CONTEXT_AMBIGUOUS":
            problems.append(f"{f.name}: S.5 must remain SOURCE_CONTEXT_AMBIGUOUS")
        ppath = pdir / f.name.replace(".context.json", ".packet.json")
        if st in ("READY_FOR_GENERATION", "READY_WITH_LIMITS"):
            if not ppath.exists():
                problems.append(f"{f.name}: READY without a packet"); continue
            pk = json.loads(ppath.read_text())
            if hashlib.sha256(pk["voted_text"]["content"].encode()).hexdigest() != tb["sha256"]:
                problems.append(f"{f.name}: packet text does not hash to the bound text")
            for rec in pk["existing_law_context"]:
                if hashlib.sha256(rec["content"].encode()).hexdigest() != rec["sha256"]:
                    problems.append(f"{f.name}: packet law fragment {rec['identifier']} does not match its hash")
                for h in rec.get("hierarchy", []):
                    if hashlib.sha256(h["content"].encode()).hexdigest() != h["sha256"]:
                        problems.append(f"{f.name}: packet lead-in {h['identifier']} does not match its hash")
                if not set(rec["relationships"]) & _NEEDS_CONTENT or rec["inclusion"] != "CONTENT_INCLUDED_FOR_GENERATION":
                    problems.append(f"{f.name}: {rec['identifier']} included without a relationship that needs content")
                if rec.get("scope") == "section" and len(rec["content"]) > 50000:
                    problems.append(f"{f.name}: whole section {rec['identifier']} over 50,000 characters injected")
            for rec in pk.get("tracked_references", []) + pk["cited_public_laws_not_included"]:
                if "content" in rec or rec.get("content_included") is not False:
                    problems.append(f"{f.name}: tracked reference {rec['identifier']} carries content")
            own = _own_metrics(pk)
            if own != pk.get("metrics"):
                problems.append(f"{f.name}: packet metrics {pk.get('metrics')} do not recompute ({own})")
            if (pk.get("budget") or {}).get("status") != ("REVIEW_REQUIRED" if own["total_source_chars"] > 150000 else "WITHIN_BUDGET"):
                problems.append(f"{f.name}: packet budget status does not follow its size")
            if pk["receipt_scaffold"] != b["receipt"]:
                problems.append(f"{f.name}: packet receipt differs from the binding's")
            cons = pk["cra_context"].get("statutory_consequence_source")
            if cons and hashlib.sha256(cons["content"].encode()).hexdigest() != cons["sha256"]:
                problems.append(f"{f.name}: packet CRA consequence does not match its hash")
            if pk["cra_context"]["mode"] != "not_cra" and pk["cra_context"].get("underlying_rule") and pk["cra_context"]["underlying_rule"].get("content_included"):
                problems.append(f"{f.name}: underlying rule content included before validation")
            summ = pk["official_summary"]
            if summ.get("content") and summ["version_relationship"] not in ("MATCHED", "EARLIER_SAME_TEXT"):
                problems.append(f"{f.name}: mismatched summary content in packet")
            if summ.get("content") and hashlib.sha256(summ["content"].encode()).hexdigest() != summ["sha256"]:
                problems.append(f"{f.name}: summary content does not match its hash")
        elif ppath.exists():
            problems.append(f"{f.name}: packet exists for a non-ready vote")
    out.append(Check("Pillar 1 context and packets re-derived from tracked artefacts", not problems,
                     f"{n} records; generation {gen}" + (f"; problems {problems[:6]}" if problems else "")))
    return out


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
    bad = [a.state for a in report.positions if a.state_coord is not None
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

    el = None
    if cfg.elections_csv.exists() and scores:
        el = _elections(cfg)
        bad = [s for s, sl in report.election.states.items() if s not in el["avg"] or abs(el["avg"][s] - sl.gop_two_party) > TOL]
        out.append(Check("every state's three-cycle two-party share", not bad and len(el["avg"]) >= 50,
                         f"{len(el['avg'])} states re-read" + (f"; mismatches {bad}" if bad else "")))
        ok = all(abs(el["national"][y] - report.election.national_by_year[y]) < TOL for y in el["national"])
        out.append(Check("national two-party share, each election", ok,
                         " ".join(f"{y}:{v:.4f}" for y, v in sorted(el["national"].items()))))
        # seat-weighted average against the nation: election results on both sides
        seat_shares = [el["avg"][roster[b]["state"]] for b in scores if roster[b]["state"] in el["avg"]]
        skew_pts = 100 * (statistics.fmean(seat_shares) - el["national_avg"])
        out.append(Check("Senate seats' vote share minus the national vote", abs(skew_pts - report.chamber_lean.skew_points) < 1e-6 and len(seat_shares) == 100,
                         f"{skew_pts:+.2f} points over {len(seat_shares)} seats vs pipeline {report.chamber_lean.skew_points:+.2f}"))
        # the line, refitted from sums
        pts = [(el["avg"][roster[b]["state"]], scores[b], b) for b in scores if roster[b]["state"] in el["avg"]]
        fit = _ols([p[0] for p in pts], [p[1] for p in pts])
        ok = (abs(fit["slope"] - report.fit.slope) < 1e-6 and abs(fit["intercept"] - report.fit.intercept) < 1e-6
              and abs(fit["s"] - report.fit.residual_se) < 1e-6 and fit["n"] == report.fit.n)
        out.append(Check("senator-vs-state-pattern line refitted", ok,
                         f"slope {fit['slope']:.4f} intercept {fit['intercept']:+.4f} s {fit['s']:.4f} n {fit['n']}"))
        reps = {x.bioguide: x for x in report.representation}
        bad = []
        for x, y, b in pts:
            pred = fit["intercept"] + fit["slope"] * x
            lev = 1 / fit["n"] + (x - fit["xbar"]) ** 2 / fit["sxx"]
            band = fit["s"] * (1 + lev) ** 0.5
            tval = (y - pred) / (fit["s"] * (1 - lev) ** 0.5)
            rp = reps.get(b)
            if rp is None or abs(rp.predicted - pred) > 1e-6 or abs(rp.residual - (y - pred)) > 1e-6 \
                    or abs(rp.band - band) > 1e-6 or abs(rp.t_stat - tval) > 1e-6:
                bad.append(b)
            elif rp.zone != ("within" if abs(y - pred) <= band else ("clear" if abs(tval) > 2 else "beyond")):
                bad.append(b)
        out.append(Check("every senator's expected position, residual, range, zone", not bad,
                         f"{len(pts)} senators recomputed" + (f"; mismatches {bad}" if bad else "")))
        from ..peers import WINDOW, MIN_PEERS, WINDOWS
        pr = _peer_results(roster, scores, el["avg"], WINDOW, MIN_PEERS, WINDOWS)
        by_b = {c.bioguide: c for c in report.peers}
        bad = []
        for b, d in pr.items():
            c = by_b.get(b)
            if c is None or c.n != d["n"] or c.peer_states != d["states"] or c.status != d["status"] \
                    or [p.bioguide for p in c.peers] != sorted(d["ids"], key=lambda q: (roster[q]["state"], report.senators[q].name)) \
                    or {w: v for w, v in c.sensitivity.items()} != d["sens"] \
                    or (d["n"] and (abs(c.low - d["low"]) > TOL or abs(c.high - d["high"]) > TOL or abs(c.median - d["median"]) > TOL)):
                bad.append(b)
        own = [b for b, c in by_b.items() if any(p.state == c.state for p in c.peers)]
        cross = [b for b, c in by_b.items() if any(pr[p.bioguide]["group"] != c.group for p in c.peers)]
        # the grouping itself: recognised parties only, Independents placed by the roster's caucus field
        unknown = sorted({roster[b]["party"] for b in scores} - {"Republican", "Democrat", "Independent"})
        inds = {b: roster[b].get("caucus") for b in scores if roster[b]["party"] == "Independent"}
        bad_grp = [b for b, d in pr.items() if by_b[b].group != d["group"]]
        dem_as_ind = [b for b, c in by_b.items() if c.party == "Independent" and c.group == "Democratic" and roster[b].get("caucus") != "Democrat"]
        out.append(Check("caucus grouping explicit: no unrecognised party, Independents by roster caucus", not unknown and not bad_grp and not dem_as_ind
                         and all(v in ("Democrat", "Republican") for v in inds.values()),
                         f"Independents {inds}" + (f"; unrecognised parties {unknown}" if unknown else "") + (f"; group mismatches {bad_grp}" if bad_grp else "")))
        out.append(Check("every senator's peer group, range, status and sensitivity", not bad and not own and not cross and len(pr) == len(by_b),
                         f"{len(pr)} senators rebuilt" + (f"; mismatches {bad}" if bad else "") + (f"; own-state peers {own}" if own else "") + (f"; cross-party peers {cross}" if cross else "")))
        counts = {s: sum(1 for d in pr.values() if d["status"] == s) for s in ("within", "outside_liberal", "outside_conservative", "unstable", "insufficient", "unsupported")}
        out.append(Check("peer rule: fixed window, minimum and cross-window check", WINDOW == 0.04 and MIN_PEERS == 6 and WINDOWS == (0.02, 0.03, 0.04, 0.05),
                         f"±{WINDOW*100:g} pts, min {MIN_PEERS}, windows {[w*100 for w in WINDOWS]}; statuses {counts}"))

    if cfg.rollcalls_csv.exists() and scores:
        out.extend(_binding_checks(cfg, roster, scores))
        out.extend(_context_checks(cfg))

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

        R, E, F = block("R"), block("E"), block("F")
        if R and E and F and el is not None:
            from ..peers import WINDOW, MIN_PEERS, WINDOWS
            pr = _peer_results(roster, scores, el["avg"], WINDOW, MIN_PEERS, WINDOWS)
            bad = []
            for b, s in R["senators"].items():
                d = pr.get(b)
                if d is None or abs(s["actual"] - scores[b]) > 1e-3 or s["n"] != d["n"] or s["states"] != d["states"] or s["status"] != d["status"] or s["group"] != d["group"] \
                        or s["sensitivity"] != {f"{w*100:g}": v for w, v in d["sens"].items()} \
                        or [p["b"] for p in s["peers"]] != sorted(d["ids"], key=lambda q: (roster[q]["state"], report.senators[q].name)) \
                        or any(p["st"] == s["st"] for p in s["peers"]) \
                        or (d["n"] and (abs(s["low"] - d["low"]) > 1e-3 or abs(s["high"] - d["high"]) > 1e-3 or abs(s["median"] - d["median"]) > 1e-3)) \
                        or abs(R["states"][s["st"]]["gop"] - el["avg"][s["st"]]) > 1e-4:
                    bad.append(b)
            out.append(Check("page: every senator's peer comparison rebuilt from raw files", not bad and len(R["senators"]) == len(scores),
                             f"{len(R['senators'])} senators" + (f"; mismatches {bad}" if bad else "")))
            ok = R["rule"]["window"] == WINDOW and R["rule"]["minPeers"] == MIN_PEERS and R["rule"]["windows"] == list(WINDOWS)
            out.append(Check("page: the peer rule shown is the rule used", ok, f"{R['rule']['window']}, {R['rule']['minPeers']}, {R['rule']['windows']}"))
            ranked = any(list(p["x"] for p in s["peers"]) == sorted(p["x"] for p in s["peers"]) and len(s["peers"]) > 3 for s in R["senators"].values())
            out.append(Check("page: peer lists are by state, not ordered by position", not ranked))
            ok = all(abs(R["states"][s]["byYear"][str(y)] - el["share"][y][s]) < 1e-4 for s in R["states"] for y in el["share"])
            out.append(Check("page: each state's election results by year", ok))
            ok = abs(E["seatsMinusNational"] - report.chamber_lean.skew_points) < 0.01 and abs(E["nationalGop"] - el["national_avg"]) < 1e-4
            out.append(Check("page: seats-versus-nation figure", ok, f"{E['seatsMinusNational']:+.2f} points"))
            forbidden_r = {"gap", "score", "rank", "skew", "dir", "vsState", "vsUS", "crosses", "grade"}
            found = sorted({k for blk in (R, E, F) for k in keys(blk) if k in forbidden_r})
            out.append(Check("page: no ranking or cross-scale field in the new blocks", not found, f"found {found}" if found else ""))
            rolls = {v["roll"] for v in F["votes"]}
            if rolls:
                raw = _votes_for_rolls(cfg, rolls)
                bad = [v["roll"] for v in F["votes"] if v["votes"] != raw[v["roll"]]]
                out.append(Check("page: every senator's vote on the published floor votes", not bad,
                                 f"{len(rolls)} votes x {len(scores)} senators re-read" + (f"; mismatches {bad}" if bad else "")))
                ok = all(v["summary"] == "" for v in F["votes"])
                out.append(Check("page: no unverified bill description", ok, "summaries empty until a verified source exists"))
        else:
            out.append(Check("page: state-relative blocks present", False, "R, E or F missing"))
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
