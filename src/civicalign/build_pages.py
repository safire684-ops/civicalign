"""Build the Pillars 4-6 pages from the saved Engine B results and the methodology registry.

    PYTHONPATH=src python -m civicalign.build_pages [--out DIR] [--check]

Reads only
    the latest saved result record     data/ideology/metrics/<key>.json (via compute.index / load_record)
    the methodology registry           ideology/methodology.py
    the three Pillar 4 anchors         data/ideology/reference_anchors.jsonl (via anchors.current)
    official committee names          data/ideology/committee_names.jsonl (congress-legislators committee list)
and writes the published pages
    demo/senator-check.html            the three views, data embedded
    demo/methodology.html              every registry entry, with this build's versions
from the templates in src/civicalign/templates/ (outside demo/, which is what the
site publishes). Nothing is calculated here: every number
is a value from the record (or an anchor record), rounded for display to the
registry's decimals, and carries the id of its registry entry so the page can
show its methodology. A number whose path has no registry entry stops the build.

A committee whose code has no official name in committee_names stops the
build: a name is never guessed.

No Engine A import, no Pillar 1 content, no 0-100 display.
"""
import argparse
import html
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .config import DEFAULT, Config
from .ideology import anchors as A
from .ideology import compute as C
from .ideology import methodology as M
from .ideology.store import Table, sha
from .sources.population import USPS

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = Path(__file__).resolve().parent / "templates"
OUT = ROOT / "demo"
PAGES = ("senator-check.html", "methodology.html")
STATE_NAMES = {v: k for k, v in USPS.items()}

# Differences keep their sign on display.
SIGNED = {"p5.weighting_difference", "p5.median_difference", "p6.committee_senate_drift",
          "p4.distance", "p5.chamber_public_gap", "p6.committee_public_drift"}
VIEW_TITLES = {"senator_state": "Senator / State (Pillar 4)", "senate_nation": "Senate / Nation (Pillar 5)",
               "committee_senate_nation": "Committee / Senate / Nation (Pillar 6)"}


class BuildError(RuntimeError):
    pass


# ---- formatting --------------------------------------------------------------------------

def fmt(value, decimals, signed=False) -> str:
    """Rounded half-up from the stored decimal text; U+2212 for minus; + only on differences."""
    if decimals is None:
        return f"{value:,}"
    d = Decimal(repr(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    if d == 0:
        d = abs(d)
    text = f"{abs(d):.{decimals}f}"
    return ("\u2212" if d < 0 else "+" if signed and d > 0 else "") + text


def _word(w: str) -> str:
    return "-".join(("Mc" + p[2:].capitalize()) if p.upper().startswith("MC") and len(p) > 2 else p.capitalize()
                    for p in w.split("-"))


def surname(voteview: str) -> str:
    """'BLUNT ROCHESTER, Lisa' -> 'Blunt Rochester'"""
    return " ".join(_word(w) for w in voteview.partition(", ")[0].split())


def display_name(voteview: str) -> str:
    """'MCCONNELL, Addison Mitchell (Mitch)' -> 'Mitch McConnell'; 'KING, Angus Stanley, Jr.' -> 'Angus King Jr.'"""
    last, _, rest = voteview.partition(", ")
    suffix = ""
    m = re.search(r",\s*(Jr\.|Sr\.|II|III|IV)$", rest)
    if m:
        suffix, rest = " " + m.group(1), rest[:m.start()]
    nick = re.search(r"\(([^)]+)\)", rest)
    first = nick.group(1) if nick else (rest.split() or [""])[0]
    return f"{first} {surname(voteview)}{suffix}".strip()


def en_dash_years(text: str) -> str:
    return re.sub(r"(\d{4})-(\d{4})", "\\1\u2013\\2", text)


def short(h: str) -> str:
    return h[:12] + "\u2026" if isinstance(h, str) and re.fullmatch(r"[0-9a-f]{40,64}", h) else h


def version_lines(value, prefix="") -> list[str]:
    """A record 'versions' value as readable lines (hashes shortened, nothing dropped but their tails)."""
    if isinstance(value, dict):
        out = []
        for k, v in value.items():
            out += version_lines(v, f"{prefix}{k.replace('_', ' ')}: " if not isinstance(v, (dict, list)) else f"{prefix}{k.replace('_', ' ')} \u2014 ")
        return out
    if isinstance(value, list):
        if value and all(isinstance(v, int) for v in value):     # a Congress range [first, last]
            return [f"{prefix.rstrip(' —')}: {chr(8211).join(str(v) for v in value)}"]
        return [l for v in value for l in version_lines(v, prefix)]
    return [f"{prefix}{short(value) if value is not None else 'none'}"]


# ---- the data the page renders -------------------------------------------------------------

def number(path: str, q: dict, entry_id: str | None = None) -> dict:
    """One displayed number: value, display text, status, reason, units and its registry entry."""
    e = M.REGISTRY[entry_id] if entry_id else M.entry_for(path)
    out = {"m": e["id"], "p": path, "s": q["status"], "u": q["units"], "r": q.get("reason"), "v": q.get("value")}
    out["d"] = fmt(q["value"], e["decimals"], e["id"] in SIGNED) if q.get("value") is not None else None
    if "standard_error" in q:
        out["se"] = fmt(q["standard_error"], e["decimals"])
    if "survey_period" in q:
        out["period"] = q["survey_period"]
    return out


def count(path: str, value: int) -> dict:
    e = M.entry_for(path)
    if e["kind"] != "count":
        raise BuildError(f"{path} is registered as {e['kind']}, not a count")
    return {"m": e["id"], "p": path, "s": "AVAILABLE", "u": e["units"], "r": None, "v": value, "d": fmt(value, None)}


def committee_names(cfg: Config, codes) -> dict[str, dict]:
    """code -> the stored official-name record; a code without one stops the build."""
    names = {r["committee_id"]: r for r in Table(cfg.ideology_dir, "committee_names").current()}
    missing = sorted(c for c in codes if c not in names)
    if missing:
        raise BuildError(f"no official committee name for {missing} in committee_names: run ingest "
                         "(source: congress-legislators committees-current.json)")
    return names


def latest(cfg: Config) -> dict:
    idx = C.index(cfg)
    if not idx:
        raise BuildError("no saved result record: run compute")
    entry = idx[-1]
    mdir, _ = C.paths(cfg)
    body = (mdir / f"{entry['input_key']}.json").read_text().rstrip("\n")
    if sha(body) != entry["content_sha256"]:
        raise BuildError(f"result {entry['input_key']} does not match its index hash")
    return json.loads(body)


def methods_payload(record: dict, anchors: list[dict]) -> dict:
    out = {}
    for e in M.ENTRIES:
        if e["kind"] == "reference":
            versions = [f"{a['display_name']}: " + "; ".join(version_lines({k: a[k] for k in e["versions"]})) for a in anchors]
        else:
            versions = [l for k in e["versions"] for l in version_lines(record["versions"][k], f"{k.replace('_', ' ')} \u2014 ")]
        out[e["id"]] = {"label": e["label"], "units": e["units"], "views": [VIEW_TITLES[v] for v in e["views"]],
                        "placement": e["placement"], "transformation": e["transformation"], "formula": e["formula"],
                        "sources": [M.SOURCES[s]["name"] + (f" ({M.SOURCES[s]['citation']})" if M.SOURCES[s]["citation"] else "")
                                    for s in e["sources"]],
                        "versions": versions, "limitations": list(e["limitations"]), "not_available": e["not_available"]}
    return out


def payload(cfg: Config = DEFAULT) -> dict:
    record = latest(cfg)
    problems = M.problems() + M.coverage(record)
    anchors = A.current(cfg)
    problems += M.anchor_problems(anchors)
    if problems:
        raise BuildError("methodology registry does not cover this record: " + "; ".join(problems))
    res = record["results"]
    p5, p6 = res["pillar5"], res["pillar6"]
    states: dict[str, list] = {}
    anchor_names = {a["bioguide_id"]: a["display_name"] for a in anchors}
    for i, s in enumerate(res["pillar4"]):
        base = f"pillar4.{i}"
        states.setdefault(s["state"], []).append({
            "id": s["bioguide_id"], "name": anchor_names.get(s["bioguide_id"]) or display_name(s["name"]),
            "short": surname(s["name"]),
            **{k: number(f"{base}.{k}", s[k]) for k in ("senator_score", "state_public_estimate", "state_on_senator_scale", "distance")}})
    anchor_rows = [{"id": a["anchor_id"], "name": a["display_name"], "short": a["display_name"].split()[-1],
                    "basis": en_dash_years(a["record_basis"]), "bioguide": a["bioguide_id"],
                    "score": number(f"reference_anchors.{a['anchor_id']}.nominate_dim1",
                                    {"value": a["nominate_dim1"], "status": "AVAILABLE", "units": M.LEGISLATOR, "reason": None},
                                    "p4.reference_anchor")} for a in anchors]
    secondary = p5["details"]["methods"][M.SECONDARY_METHOD]
    primary_label = p5["population_weighted_center"]
    names = committee_names(cfg, p6)
    committees = [{"code": c, "name": names[c]["display_name"], "official_name": names[c]["official_name"],
                   "name_source": names[c]["source"], "name_retrieved": names[c]["retrieved_at"][:10],
                   "listed": count(f"pillar6.{c}.members_listed", v["members_listed"]),
                   "scored": count(f"pillar6.{c}.members_scored", v["members_scored"]), "left_out": v["members_left_out"],
                   **{k: number(f"pillar6.{c}.{k}", v[k]) for k in ("committee_median", "committee_senate_drift", "committee_public_drift")}}
                  for c, v in p6.items()]
    v = record["versions"]
    return {
        "meta": {"input_key": record["input_key"], "input_key_short": record["input_key"][:8], "congress": v["congress"],
                 "measurement_date": v["measurement_date"], "score_column": v["legislator_model"]["score_column"],
                 "aip_wave": v["public_model"]["wave"], "bridge": f"{v['bridge']['bridge_version']} ({v['bridge']['status']})",
                 "population": f"{v['population']['vintage']}, {v['population']['measurement_year']}",
                 "committee_observed": v["committee_membership"]["latest_observed_date"],
                 "primary_method": p5["configured_method"], "method_status": primary_label["method_status"]},
        "methods": methods_payload(record, anchors),
        "p4": {"states": [{"code": st, "name": STATE_NAMES.get(st, st), "senators": sens}
                          for st, sens in sorted(states.items(), key=lambda kv: STATE_NAMES.get(kv[0], kv[0]))],
               "anchors": anchor_rows},
        "p5": {"active": count("pillar5.active_senators", p5["active_senators"]),
               "unscored": p5["unscored_seated_senators"],
               "plain": number("pillar5.plain_center", p5["plain_center"]),
               "weighted": number("pillar5.population_weighted_center", p5["population_weighted_center"]),
               "diff": number("pillar5.population_weighting_difference", p5["population_weighting_difference"]),
               "median": number("pillar5.details.chamber_median", p5["details"]["chamber_median"]),
               "wmedian": number(f"pillar5.details.methods.{M.SECONDARY_METHOD}.population_weighted_center",
                                 secondary["population_weighted_center"]),
               "mdiff": number(f"pillar5.details.methods.{M.SECONDARY_METHOD}.population_weighting_difference",
                               secondary["population_weighting_difference"]),
               "national": number("pillar5.national_public", p5["national_public"]),
               "gap": number("pillar5.chamber_public_gap", p5["chamber_public_gap"])},
        "p6": {"senate_median": number("pillar5.details.chamber_median", p5["details"]["chamber_median"]),
               "national": number("pillar5.national_public", p5["national_public"]),
               "committees": sorted(committees, key=lambda c: c["name"])},
    }


# ---- the pages -------------------------------------------------------------------------------

def embed(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")


def e(t) -> str:
    return html.escape(str(t), quote=True)


def methodology_html(data: dict) -> str:
    meta, methods = data["meta"], data["methods"]
    parts = []
    for view, title in VIEW_TITLES.items():
        parts.append(f'<h2 id="view-{view}">{e(title)}</h2>')
        for eid, m in methods.items():
            if VIEW_TITLES[view] != m["views"][0]:
                continue
            na = f'<dt>When it is not available</dt><dd>{e(m["not_available"])}</dd>' if m["not_available"] else ""
            parts.append(
                f'<section class="entry" id="{e(eid)}"><h3>{e(m["label"])} <code>{e(eid)}</code></h3><dl>'
                f'<dt>Shown in</dt><dd>{e(", ".join(m["views"]))} &middot; {e("main view" if m["placement"] == "main" else "details only")}</dd>'
                f'<dt>Units</dt><dd>{e(m["units"])}</dd>'
                f'<dt>Raw source</dt><dd><ul>{"".join(f"<li>{e(s)}</li>" for s in m["sources"])}</ul></dd>'
                f'<dt>Transformation</dt><dd>{e(m["transformation"])}</dd>'
                f'<dt>Formula</dt><dd class="formula">{e(m["formula"])}</dd>'
                f'<dt>Versions in this build</dt><dd><ul>{"".join(f"<li>{e(s)}</li>" for s in m["versions"])}</ul></dd>'
                f'<dt>Limitations</dt><dd><ul>{"".join(f"<li>{e(s)}</li>" for s in m["limitations"])}</ul></dd>{na}</dl></section>')
    anchors = "".join(f'<tr><td>{e(a["name"])}</td><td class="n">{e(a["score"]["d"])}</td><td>{e(a["basis"])}</td></tr>'
                      for a in data["p4"]["anchors"])
    body = (f'<p class="asof">Result record <code>{e(meta["input_key"])}</code> &middot; measurement date '
            f'{e(meta["measurement_date"])} &middot; {e(meta["congress"])}th Congress &middot; score column '
            f'<code>{e(meta["score_column"])}</code> &middot; bridge {e(meta["bridge"])}</p>'
            f'<h2 id="anchors">Pillar 4 reference figures</h2><p>Visual reference points only. They are never an input to '
            f'any calculation.</p><table class="anchors"><tr><th>Figure</th><th>Score</th><th>Record used</th></tr>{anchors}</table>'
            + "".join(parts))
    return body


def build(cfg: Config = DEFAULT) -> dict[str, str]:
    data = payload(cfg)
    page = (TEMPLATES / "senator-check.template.html").read_text()
    report = (TEMPLATES / "methodology.template.html").read_text()
    for marker, text in (("<!--DATA-->", page), ("<!--METHODOLOGY-->", report)):
        if text.count(marker) != 1:
            raise BuildError(f"template must contain {marker} exactly once")
    return {"senator-check.html": page.replace("<!--DATA-->", f'<script id="data" type="application/json">{embed(data)}</script>'),
            "methodology.html": report.replace("<!--METHODOLOGY-->", methodology_html(data))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    a = ap.parse_args()
    try:
        pages = build(DEFAULT)
    except (BuildError, A.AnchorError) as err:
        print(f"BUILD REFUSED: {err}", file=sys.stderr)
        return 1
    if a.check:
        stale = [n for n, t in pages.items() if not (a.out / n).exists() or (a.out / n).read_text() != t]
        print("pages are current" if not stale else f"stale: {stale}")
        return 1 if stale else 0
    a.out.mkdir(parents=True, exist_ok=True)
    for n, t in pages.items():
        (a.out / n).write_text(t)
    print(f"wrote {', '.join(str(a.out / n) for n in pages)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
