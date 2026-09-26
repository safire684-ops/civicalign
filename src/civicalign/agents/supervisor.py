"""The supervisor: an independent recount of every published number before publishing.

WHY THIS EXISTS
---------------
The Engine B code reads the raw files with one set of code and most tests check
that the pages agree with it. If that code misreads a file, both agree and both
are wrong. This module reads the same raw files with its own, deliberately
separate code, recomputes each published figure from scratch, and compares. Any
disagreement fails the update, so nothing is published.

Engine B (Pillars 4-6), from the raw snapshot files and the stored records:
  * every senator's nominate_dim1 re-read from Voteview, for every stored row and
    every seated senator in the result; every state public estimate and its
    standard error re-read from the American Ideology Project file
  * Pillar 5: the Senate mean, the population-weighted Senate mean and their
    difference, and in details the Senate median, the population-weighted
    median and their difference, recomputed with separate arithmetic from the
    roster, Voteview and the Census file
  * Pillar 6: every standing committee's median and its drift from the Senate
    median, recomputed from the committee membership file
  * the three Pillar 4 anchors against the Voteview file, and on the page
  * the committee names against the official congress-legislators list
  * gating: no senator-to-state distance while the bridge is NONE; no
    Senate-to-public gap and no committee-to-public drift while the national
    estimate is unresolved -- in the record and on the page
  * every displayed number has a methodology registry entry and equals the
    record's value with that entry's rounding; every entry is on the page and
    has a methodology section
  * every stored record valid and hash-chained, the result index intact and
    current, nothing committed rewritten (append-only against the last commit),
    and the published pages equal to the builder's output

Pillar 1 (Engine A), unchanged: every vote binding and every context record and
packet re-derived from Pillar 1's own cached first-party files (pillar1_checks).

Run:  PYTHONPATH=src python -m civicalign.agents.supervisor
Exit 0 means every figure was independently confirmed.
"""
import csv
import json
import re
import sys
from dataclasses import dataclass
from fractions import Fraction
from math import fsum
from pathlib import Path

from ..config import DEFAULT, Config

TOL = 1e-6
DEMO = Path(__file__).resolve().parents[3] / "demo"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""

    def line(self) -> str:
        return f"  {'ok  ' if self.ok else 'FAIL'}  {self.name:46s} {self.detail}"


# ---- independent readers shared with Pillar 1 --------------------------------------

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


# ==== Engine B (Pillars 4-6): an independent recount of every published number ====================
#
# The readers below parse the raw snapshot files with their own code: they do not
# call ideology/ingest.py or ideology/pillars.py. Their results are compared with
# the stored input tables, the latest saved result record, the stored anchors and
# committee names, and the numbers embedded in the published page.

def _eb_members(cfg: Config) -> list[dict]:
    with cfg.members_csv.open() as fh:
        return list(csv.DictReader(fh))


def _eb_seated(cfg: Config) -> dict[str, str]:
    """bioguide -> state for every senator the roster lists as seated."""
    out = {}
    for p in json.loads(cfg.roster_json.read_text()):
        t = p["terms"][-1]
        if t["type"] == "sen":
            out[p["id"]["bioguide"]] = t["state"]
    return out


def _eb_populations(cfg: Config) -> dict[str, int]:
    from ..sources.population import USPS    # a name -> code table, not a calculation
    col = f"POPESTIMATE{cfg.pillar5_population_year}"
    out = {}
    with cfg.population_csv.open(encoding="latin-1") as fh:
        for row in csv.DictReader(fh):
            if row.get("SUMLEV") == "040" and row["NAME"] in USPS:
                out[USPS[row["NAME"]]] = int(row[col])
    return out


def _eb_publics(cfg: Config) -> dict[str, tuple[float, float]]:
    out = {}
    with cfg.ideology_tab.open() as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if int(row["presidential_year"]) == cfg.pillars_aip_wave:
                out[row["abb"].strip().strip('"')] = (float(row["mrp_ideology"]), float(row["mrp_ideology_se"]))
    return out


def _eb_committees(cfg: Config) -> dict[str, list[str]]:
    data = json.loads(cfg.committees_json.read_text())
    p = cfg.standing_committee_prefix
    return {c: [m["bioguide"] for m in ms if m.get("bioguide")] for c, ms in data.items() if c.startswith(p) and len(c) == 4}


def _eb_committee_names(cfg: Config) -> dict[str, str]:
    """code -> official name for every Senate standing committee in the official list."""
    return {c["thomas_id"]: c["name"].strip() for c in json.loads(cfg.committee_list_json.read_text())
            if c.get("type") == "senate" and str(c.get("thomas_id", "")).startswith(cfg.standing_committee_prefix)}


def _eb_short_name(official: str) -> str | None:
    for prefix in ("Senate Committee on the ", "Senate Committee on "):
        if official.startswith(prefix) and len(official) > len(prefix):
            return official[len(prefix):]
    return None


def _eb_median(xs: list[float]) -> float:
    s = sorted(xs); n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _eb_weighted_median(points: list[tuple[float, Fraction]]) -> float:
    pts = sorted(points, key=lambda p: p[0])
    half, run = sum(w for _, w in pts) / 2, Fraction(0)
    for i, (x, w) in enumerate(pts):
        run += w
        if run == half:
            return (x + pts[i + 1][0]) / 2
        if run > half:
            return x
    raise ValueError("weights never reached half")


def _eb_close(a, b, tol: float = 1e-9) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def _eb_half_up(value: float, decimals: int, signed: bool) -> str:
    """The page's display rule, re-implemented: half-up from the stored decimal text, U+2212 for minus."""
    from decimal import ROUND_HALF_UP, Decimal
    d = Decimal(repr(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    if d == 0:
        d = abs(d)
    return ("−" if d < 0 else "+" if signed and d > 0 else "") + f"{abs(d):.{decimals}f}"


def eb_raw(cfg: Config) -> dict:
    """Everything the Engine B recount reads from the raw snapshot files."""
    return {"members": _eb_members(cfg), "seated": _eb_seated(cfg), "populations": _eb_populations(cfg),
            "publics": _eb_publics(cfg), "committees": _eb_committees(cfg), "names": _eb_committee_names(cfg)}


def eb_recount_checks(cfg: Config, raw: dict, record: dict, senator_rows: list[dict]) -> list[Check]:
    """Senator scores, the Pillar 5 centres and every committee median and drift, recomputed from the raw files."""
    out: list[Check] = []
    col = "nominate_dim1"
    res = record["results"]
    rows = {r["bioguide_id"]: r for r in raw["members"] if r["chamber"] == "Senate" and r["congress"] == str(cfg.congress)}
    seated = raw["seated"]
    scores = {b: float(rows[b][col]) for b in seated if b in rows and rows[b][col] not in ("", None)}
    out.append(Check("Engine B: 100 seated senators in the roster", len(seated) == 100, f"{len(seated)} seated"))

    stored = {r["bioguide_id"]: r for r in senator_rows if r["congress"] == cfg.congress}
    bad = [b for b, r in rows.items() if b not in stored or not ((r[col] in ("", None) and stored[b][col] is None)
                                                                  or _eb_close(float(r[col] or "nan"), stored[b][col], 0))]
    bad += [b for b, s in stored.items() if s["seated"] != (b in seated)]
    out.append(Check("Engine B: every stored senator nominate_dim1 re-read from Voteview", not bad and len(stored) == len(rows),
                     f"{len(rows)} Voteview Senate rows" + (f"; mismatches {bad[:5]}" if bad else "")))
    shown = {s["bioguide_id"]: s["senator_score"]["value"] for s in res["pillar4"]}
    bad = [b for b in seated if (shown.get(b) if b in shown else "missing") != scores.get(b)]
    out.append(Check("Engine B: every seated senator's score in the result", not bad and set(shown) == set(seated),
                     f"{len(shown)} senators" + (f"; mismatches {bad[:5]}" if bad else "")))
    pub = raw["publics"]
    bad = [s["state"] for s in res["pillar4"] if not (_eb_close(s["state_public_estimate"]["value"], pub.get(s["state"], (None,))[0], 0)
                                                      and _eb_close(s["state_public_estimate"]["standard_error"], pub[s["state"]][1], 0))]
    out.append(Check("Engine B: every state public estimate and standard error re-read", not bad,
                     f"AIP wave {cfg.pillars_aip_wave}" + (f"; mismatches {bad[:5]}" if bad else "")))

    # Pillar 5: weights = state population / senators the state has seated; an unscored senator's share is left out
    pops = raw["populations"]
    per_state: dict[str, int] = {}
    for b, st in seated.items():
        per_state[st] = per_state.get(st, 0) + 1
    active = sorted(scores)
    xs = [scores[b] for b in active]
    ws = [Fraction(pops[seated[b]], per_state[seated[b]]) for b in active]
    plain_mean = fsum(xs) / len(xs)
    weighted_mean = float(sum(Fraction(x) * w for x, w in zip(xs, ws)) / sum(ws))
    median = _eb_median(xs)
    wmedian = _eb_weighted_median(list(zip(xs, ws)))
    p5 = res["pillar5"]
    m_mean = p5["details"]["methods"]["population_weighted_mean_v1"]
    m_med = p5["details"]["methods"]["population_weighted_median_v1"]
    pairs = [
        ("Pillar 5 Senate mean (each senator counted equally)", plain_mean, [p5["plain_center"], p5["details"]["chamber_mean"], m_mean["plain_center"]]),
        ("Pillar 5 population-weighted Senate mean", weighted_mean, [p5["population_weighted_center"], m_mean["population_weighted_center"]]),
        ("Pillar 5 population weighting difference", plain_mean - weighted_mean,
         [p5["population_weighting_difference"], m_mean["population_weighting_difference"]]),
        ("Pillar 5 details: Senate median", median, [p5["details"]["chamber_median"], m_med["plain_center"]]),
        ("Pillar 5 details: population-weighted median", wmedian, [m_med["population_weighted_center"]]),
        ("Pillar 5 details: median difference", median - wmedian, [m_med["population_weighting_difference"]]),
    ]
    for name, mine, stored_qs in pairs:
        ok = all(_eb_close(mine, q["value"]) for q in stored_qs)
        out.append(Check(f"Engine B: {name}", ok, f"{mine:+.6f} vs record " + ", ".join(f"{q['value']:+.6f}" for q in stored_qs)))
    out.append(Check("Engine B: Pillar 5 senators included", p5["active_senators"] == len(active),
                     f"{len(active)} recounted, {p5['active_senators']} in the record"))
    out.append(Check("Engine B: Pillar 5 main result is the primary method", p5["configured_method"] == "population_weighted_mean_v1"
                     and p5["population_weighted_center"]["role"] == "PRIMARY", p5["configured_method"]))

    # Pillar 6: every standing committee's median and its drift from the Senate median
    p6 = res["pillar6"]
    bad_median, bad_drift = [], []
    for code, members in raw["committees"].items():
        sc = [scores[b] for b in members if b in scores]
        rec = p6.get(code)
        if rec is None:
            bad_median.append(f"{code} missing from the record"); bad_drift.append(code); continue
        cm = _eb_median(sc) if sc else None
        if rec["members_listed"] != len(members) or rec["members_scored"] != len(sc):
            bad_median.append(f"{code} member counts")
        if not _eb_close(cm, rec["committee_median"]["value"]):
            bad_median.append(f"{code} median")
        if not _eb_close(cm - median if cm is not None else None, rec["committee_senate_drift"]["value"]):
            bad_drift.append(code)
    bad_median += [f"{c} not in the membership file" for c in p6 if c not in raw["committees"]]
    out.append(Check("Engine B: every committee median recomputed", not bad_median,
                     f"{len(raw['committees'])} committees" + (f"; {bad_median[:5]}" if bad_median else "")))
    out.append(Check("Engine B: every committee-to-Senate drift recomputed", not bad_drift,
                     "committee median - Senate median, sign kept" + (f"; mismatches {bad_drift[:5]}" if bad_drift else "")))
    return out


def eb_anchor_checks(cfg: Config, raw: dict, anchor_rows: list[dict], page_data: dict | None) -> list[Check]:
    """The three Pillar 4 anchors against the Voteview file: one Senate id each, one career score each."""
    from ..ideology.anchors import ANCHORS
    bad = []
    stored = {a["anchor_id"]: a for a in anchor_rows}
    for spec in ANCHORS:
        ids = {r["icpsr"] for r in raw["members"] if r["bioguide_id"] == spec["bioguide_id"] and r["chamber"] == "Senate"}
        vals = {r["nominate_dim1"] for r in raw["members"] if r["icpsr"] in ids and r["chamber"] in ("House", "Senate") and r["nominate_dim1"]}
        a = stored.get(spec["anchor_id"])
        if len(ids) != 1 or len(vals) != 1 or a is None or a["nominate_dim1"] != float(next(iter(vals))) or a["voteview_icpsr"] != next(iter(ids)):
            bad.append(spec["anchor_id"])
    ok = not bad and len(ANCHORS) == 3 and set(stored) == {s["anchor_id"] for s in ANCHORS}
    out = [Check("Engine B: three anchors match the Voteview source", ok,
                 ", ".join(f"{a['display_name']} {a['nominate_dim1']:+.3f}" for a in anchor_rows) + (f"; mismatches {bad}" if bad else ""))]
    if page_data is not None:
        shown = {a["id"]: a["score"]["v"] for a in page_data["p4"]["anchors"]}
        ok = (shown == {k: v["nominate_dim1"] for k, v in stored.items()} and len(shown) == 3
              and all(a["score"]["m"] == "p4.reference_anchor" for a in page_data["p4"]["anchors"])
              and "reference_anchor" not in json.dumps({k: page_data[k] for k in ("p5", "p6")}))
        out.append(Check("Engine B: page shows exactly the stored anchors, in Pillar 4 only", ok, f"{len(shown)} on the page"))
    return out


def eb_name_checks(raw: dict, name_rows: list[dict], record: dict, page_data: dict | None) -> list[Check]:
    stored = {r["committee_id"]: r for r in name_rows}
    bad = [c for c, official in raw["names"].items() if c not in stored or stored[c]["official_name"] != official
           or stored[c]["display_name"] != _eb_short_name(official)]
    bad += [c for c in stored if c not in raw["names"]]
    missing = sorted(c for c in record["results"]["pillar6"] if c not in stored)
    out = [Check("Engine B: committee names match the official list", not bad and not missing,
                 f"{len(stored)} names" + (f"; mismatches {bad}" if bad else "") + (f"; no name for {missing}" if missing else ""))]
    if page_data is not None:
        pbad = [c["code"] for c in page_data["p6"]["committees"] if c["code"] not in stored or c["name"] != stored[c["code"]]["display_name"]
                or c["official_name"] != stored[c["code"]]["official_name"]]
        out.append(Check("Engine B: page committee names are the official names", not pbad, f"mismatches {pbad}" if pbad else ""))
    return out


def eb_gating_checks(record: dict, bridge_status: str, page_data: dict | None) -> list[Check]:
    """Nothing that needs the bridge or a national estimate may carry a value while they are unavailable."""
    res = record["results"]
    na = lambda q: q["status"] == "NOT_AVAILABLE" and q["value"] is None and bool(q["reason"])
    out = []
    if bridge_status == "NONE":
        bad = [s["bioguide_id"] for s in res["pillar4"] if not (na(s["distance"]) and na(s["state_on_senator_scale"]))]
        out.append(Check("Engine B: no senator-to-state distance while the bridge is NONE", not bad,
                         f"{len(res['pillar4'])} senators" + (f"; values present {bad[:5]}" if bad else "")))
    p5 = res["pillar5"]
    out.append(Check("Engine B: no Senate-to-public gap while the national estimate is unresolved",
                     na(p5["national_public"]) and na(p5["chamber_public_gap"]) and p5["national_public"].get("definition_status") == "UNRESOLVED"))
    bad = [c for c, v in res["pillar6"].items() if not na(v["committee_public_drift"])]
    out.append(Check("Engine B: no committee-to-public drift while bridge and national estimate are unavailable", not bad,
                     f"values present {bad}" if bad else f"{len(res['pillar6'])} committees"))
    if page_data is not None:
        nums = list(_eb_numbers(page_data))
        gated = [n for n in nums if n["m"] in ("p4.distance", "p4.state_on_senator_scale", "p5.national_public",
                                               "p5.chamber_public_gap", "p6.committee_public_drift")]
        bad = [n["p"] for n in gated if n["s"] != "NOT_AVAILABLE" or n["v"] is not None or n["d"] is not None or not n["r"]]
        out.append(Check("Engine B: the page shows those as not available, with a reason", not bad and bool(gated),
                         f"{len(gated)} gated numbers" + (f"; shown with a value {bad[:5]}" if bad else "")))
    return out


def _eb_numbers(obj):
    if isinstance(obj, dict):
        if "m" in obj and "s" in obj:
            yield obj
        else:
            for v in obj.values():
                yield from _eb_numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _eb_numbers(v)


def _eb_resolve(results: dict, path: str):
    node = results
    for part in path.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def eb_page_data(page_html: str) -> dict | None:
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', page_html, re.S)
    return json.loads(m.group(1)) if m else None


def eb_methodology_checks(record: dict, anchor_rows: list[dict], page_data: dict | None, methodology_html: str | None) -> list[Check]:
    """Every displayed number has a registry entry, and the page shows the record's value with that entry's rounding."""
    from ..ideology import methodology as M
    probs = M.problems() + M.coverage(record) + M.anchor_problems(anchor_rows)
    out = [Check("Engine B: methodology registry covers every number in the record", not probs, "; ".join(probs[:3]))]
    if page_data is None:
        out.append(Check("Engine B: the published page carries its data", False, "no embedded data found"))
        return out
    nums = list(_eb_numbers(page_data))
    signed = {"p5.weighting_difference", "p5.median_difference", "p6.committee_senate_drift", "p4.distance",
              "p5.chamber_public_gap", "p6.committee_public_drift"}
    bad = []
    for n in nums:
        e = M.REGISTRY.get(n["m"])
        if e is None:
            bad.append(f"{n['p']}: no entry"); continue
        if n["p"].startswith("reference_anchors."):
            continue
        try:
            q = _eb_resolve(record["results"], n["p"])
        except (KeyError, IndexError, ValueError):
            bad.append(f"{n['p']}: not in the record"); continue
        v = q if isinstance(q, int) and not isinstance(q, bool) else q["value"]
        if v != n["v"]:
            bad.append(f"{n['p']}: page {n['v']} vs record {v}")
        elif v is not None and n["d"] != (f"{v:,}" if e["decimals"] is None else _eb_half_up(v, e["decimals"], e["id"] in signed)):
            bad.append(f"{n['p']}: display {n['d']}")
    out.append(Check("Engine B: every displayed number has methodology and equals the record", not bad,
                     f"{len(nums)} numbers" + (f"; {bad[:5]}" if bad else "")))
    ids = {n["m"] for n in nums}
    missing_page = sorted(set(M.REGISTRY) - ids)
    missing_doc = sorted(i for i in M.REGISTRY if methodology_html is None or f'id="{i}"' not in methodology_html)
    out.append(Check("Engine B: every registry entry is on the page and in the methodology page", not missing_page and not missing_doc,
                     f"{len(M.REGISTRY)} entries" + (f"; not shown {missing_page}" if missing_page else "") + (f"; no methodology section {missing_doc}" if missing_doc else "")))
    return out


def _eb_git_head(path: Path) -> str | None:
    import subprocess
    root = Path(__file__).resolve().parents[3]
    try:
        rel = path.resolve().relative_to(root)
        r = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{rel.as_posix()}"], capture_output=True, text=True, timeout=30)
    except (ValueError, OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def eb_store_checks(cfg: Config) -> list[Check]:
    """Every versioned table re-verified, the result index intact, and nothing committed rewritten or removed."""
    from ..ideology import compute as C
    from ..ideology import records as R
    from ..ideology.store import Table
    out = []
    probs = {t: Table(cfg.ideology_dir, t).verify() for t in R.TABLES}
    bad = {t: p[:2] for t, p in probs.items() if p}
    out.append(Check("Engine B: every stored record valid and hash-chained", not bad, f"{len(R.TABLES)} tables" + (f"; {bad}" if bad else "")))
    cp = C.verify(cfg)
    out.append(Check("Engine B: result records indexed, unaltered and current", not cp, "; ".join(cp[:3])))
    rewritten = []
    files = sorted(cfg.ideology_dir.glob("*.jsonl")) + sorted((cfg.ideology_dir / "metrics").glob("*.json"))
    for f in files:
        head = _eb_git_head(f)
        if head is None:
            continue           # not committed yet: nothing to be append-only against
        now = f.read_text()
        if f.suffix == ".json" and now != head:
            rewritten.append(f.name)
        elif f.suffix == ".jsonl" and not now.startswith(head):
            rewritten.append(f.name)
    out.append(Check("Engine B: stored records append-only against the last commit", not rewritten,
                     f"{len(files)} files" + (f"; rewritten {rewritten}" if rewritten else "")))
    return out


def eb_page_current_checks(cfg: Config, page_dir: Path) -> list[Check]:
    from ..build_pages import build
    try:
        expected = build(cfg)
    except Exception as e:                      # a build refusal is itself a failed check
        return [Check("Engine B: published pages are the builder's output", False, f"build refused: {e}")]
    stale = [n for n, t in expected.items() if not (page_dir / n).exists() or (page_dir / n).read_text() != t]
    return [Check("Engine B: published pages are the builder's output", not stale, f"stale {stale}" if stale else "")]


def engine_b_checks(cfg: Config = DEFAULT, page_dir: Path | None = None) -> list[Check]:
    from ..ideology import bridge as BR
    from ..ideology import compute as C
    from ..ideology.store import Table
    page_dir = page_dir if page_dir is not None else DEMO
    idx = C.index(cfg)
    if not idx:
        return [Check("Engine B: a saved result record exists", False, "run compute")]
    record = C.load_record(cfg, idx[-1]["input_key"])
    raw = eb_raw(cfg)
    anchors = Table(cfg.ideology_dir, "reference_anchors").current()
    names = Table(cfg.ideology_dir, "committee_names").current()
    page = page_dir / "senator-check.html"
    page_data = eb_page_data(page.read_text()) if page.exists() else None
    meth = (page_dir / "methodology.html").read_text() if (page_dir / "methodology.html").exists() else None
    out = eb_recount_checks(cfg, raw, record, Table(cfg.ideology_dir, "senator_ideology").current())
    out += eb_anchor_checks(cfg, raw, anchors, page_data)
    out += eb_name_checks(raw, names, record, page_data)
    out += eb_gating_checks(record, BR.active(cfg)["status"], page_data)
    out += eb_methodology_checks(record, anchors, page_data, meth)
    out += eb_store_checks(cfg)
    out += eb_page_current_checks(cfg, page_dir)
    return out


# ==== Pillar 1 (Engine A): unchanged ==========================================================

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

def pillar1_checks(cfg: Config = DEFAULT) -> list[Check]:
    """Only the Pillar 1 (Engine A) checks: the vote bindings, and the context and
    packets, each re-derived from Pillar 1's own cached first-party files. They
    need neither the pipeline report nor any page. The same functions, with the
    same inputs and the same condition, that checks() runs."""
    roster = _roster(cfg)
    scores = _scores(cfg, roster)
    if not (cfg.rollcalls_csv.exists() and scores):
        return []
    return _binding_checks(cfg, roster, scores) + _context_checks(cfg)


def checks(cfg: Config = DEFAULT, page_dir: Path | None = None) -> list[Check]:
    """Everything: the Engine B recount and the Pillar 1 checks."""
    return engine_b_checks(cfg, page_dir) + pillar1_checks(cfg)


def main() -> int:
    print("Supervisor: independent recount of every published figure\n")
    results = checks(DEFAULT)
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
