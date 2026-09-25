"""Versioned Pillars 4-6 results, recomputed only where their inputs changed.

    PYTHONPATH=src python -m civicalign.ideology.compute [--verify] [--full]

Each result record is keyed by its inputs: the record_id of every input
record used (senators, public estimates, populations, committee membership
events, the bridge) and every setting that changes a number (score column,
AIP wave, weighting method, population year and vintage, bridge version,
Congress). Same inputs, same key; a key is written once and never again.

    data/ideology/metrics/<input_key>.json   one result record, write-once
    data/ideology/metrics_index.jsonl        append-only list of every record, in order

Recomputation
    unchanged       the key already exists: nothing is written
    committees_only only committee membership changed: the committees whose
                    membership changed are recomputed; every other committee,
                    and Pillars 4 and 5, are carried from the previous record
                    (each result says which record computed it)
    full            anything else changed (senator scores or seats, public
                    estimates, populations, bridge, settings): everything is
                    recomputed. A new public-opinion version or bridge always
                    lands here, as does a senator-score change (it moves the
                    Senate median, and with it every committee's drift).
A carried result is always identical to what a full recompute would give
(tested). Earlier records are never overwritten or deleted.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

from ..config import DEFAULT, Config
from . import bridge as B
from . import national as N
from . import pillars as P
from .inputs import current_members
from .store import Table, canonical, sha

SCHEMA = "civicalign.ideology.metrics/1.0"


class ComputeError(RuntimeError):
    pass


def fp(ids) -> str:
    return sha(canonical(sorted(ids)))


def gather(cfg: Config) -> dict:
    """Current input lines (with their record_ids) for this Congress and these settings."""
    def lines(table):
        return list(Table(cfg.ideology_dir, table).latest().values())
    sen = [l for l in lines("senator_ideology") if l["content"]["congress"] == cfg.congress]
    pub = [l for l in lines("constituency_ideology") if l["content"]["geography_type"] == "state" and l["content"]["wave"] == cfg.pillars_aip_wave]
    pop = [l for l in lines("state_population") if l["content"]["measurement_year"] == cfg.pillar5_population_year
           and l["content"]["vintage"] == cfg.pillar5_population_vintage]
    evs = [l for l in lines("committee_membership_events") if l["content"]["congress"] == cfg.congress]
    bridges = lines("ideology_bridge")
    br = next((l for l in bridges if l["content"]["bridge_version"] == cfg.active_bridge_version), None)
    if br is None:
        raise ComputeError(f"active bridge {cfg.active_bridge_version!r} is not recorded")
    if not sen or not pub or not pop:
        raise ComputeError("missing inputs: ingest senators, public estimates and populations first")
    return {"senators": sen, "publics": pub, "populations": pop, "events": evs, "bridge": br}


def settings(cfg: Config) -> dict:
    return {"congress": cfg.congress, "score_column": cfg.pillars_score_column, "aip_wave": cfg.pillars_aip_wave,
            "weighting_method": cfg.pillar5_weighting_method, "population_year": cfg.pillar5_population_year,
            "population_vintage": cfg.pillar5_population_vintage, "bridge_version": cfg.active_bridge_version,
            "standing_committee_prefix": cfg.standing_committee_prefix}


def fingerprints(cfg: Config, g: dict) -> dict:
    by_committee: dict[str, list[str]] = {}
    for l in g["events"]:
        by_committee.setdefault(l["content"]["committee_id"], []).append(l["record_id"])
    return {"settings": sha(canonical(settings(cfg))), "senators": fp(l["record_id"] for l in g["senators"]),
            "publics": fp(l["record_id"] for l in g["publics"]), "populations": fp(l["record_id"] for l in g["populations"]),
            "bridge": g["bridge"]["record_id"], "committees": {c: fp(ids) for c, ids in sorted(by_committee.items())}}


def versions(cfg: Config, g: dict) -> dict:
    """Everything a result must be traceable to."""
    def one(lines, *fields):
        vals = {tuple(l["content"][f] for f in fields) for l in lines}
        return [dict(zip(fields, v)) for v in sorted(vals)]
    br = g["bridge"]["content"]
    retrieved = [l["content"]["retrieved_at"] for key in ("senators", "publics", "populations", "events") for l in g[key]]
    retrieved += [l["content"]["roster_retrieved_at"] for l in g["senators"]]
    latest = max(retrieved)
    return {
        "congress": cfg.congress,
        "measurement_date": latest[:10],
        "inputs_latest_retrieved_at": latest,
        "legislator_model": {"score_column": cfg.pillars_score_column,
                             "sources": one(g["senators"], "source", "source_version", "source_sha256", "retrieved_at"),
                             "roster": one(g["senators"], "roster_source_version", "roster_retrieved_at")},
        "public_model": {"wave": cfg.pillars_aip_wave,
                         "sources": one(g["publics"], "methodology_version", "source_version", "source_sha256", "retrieved_at")},
        "population": {"measurement_year": cfg.pillar5_population_year, "vintage": cfg.pillar5_population_vintage,
                       "sources": one(g["populations"], "source_version", "source_sha256", "retrieved_at")},
        "committee_membership": {"sources": one(g["events"], "source_version", "retrieved_at"),
                                 "latest_observed_date": max((l["content"]["observed_date"] for l in g["events"]), default=None),
                                 "date_basis": "observed, not official (see committee_membership_events)"},
        "bridge": {"bridge_version": br["bridge_version"], "status": br["status"], "record_id": g["bridge"]["record_id"]},
        "weighting": {"primary_method": cfg.pillar5_weighting_method, "methods_computed": sorted(P.WEIGHTING_METHODS)},
        "national_public": "UNRESOLVED",
    }


def _calculate(cfg: Config, g: dict, committees: set[str] | None) -> dict:
    col = cfg.pillars_score_column
    senators = [l["content"] for l in g["senators"]]
    bridge = g["bridge"]["content"]
    nat = N.national(bridge)
    out = {}
    p5 = P.pillar5(senators, {l["content"]["geography_id"]: l["content"]["population"] for l in g["populations"]}, nat, col,
                   cfg.pillar5_weighting_method)
    members = current_members([l["content"] for l in g["events"]], cfg.congress)
    if committees is not None:
        members = {c: m for c, m in members.items() if c in committees}
    out["pillar6"] = P.pillar6(members, senators, p5["details"]["chamber_median"]["value"], nat, col)
    if committees is None:
        out["pillar5"] = p5
        out["pillar4"] = P.pillar4(senators, {l["content"]["geography_id"]: l["content"] for l in g["publics"]}, bridge, col,
                                   cfg.pillars_aip_wave)
    return out


def paths(cfg: Config):
    return cfg.ideology_dir / "metrics", cfg.ideology_dir / "metrics_index.jsonl"


def index(cfg: Config) -> list[dict]:
    _, ip = paths(cfg)
    return [json.loads(l) for l in ip.read_text().splitlines() if l.strip()] if ip.exists() else []


def load_record(cfg: Config, key: str) -> dict:
    mdir, _ = paths(cfg)
    return json.loads((mdir / f"{key}.json").read_text())


def plan(cfg: Config, force_full: bool = False) -> dict:
    """What compute() would do, without writing."""
    g = gather(cfg)
    fps = fingerprints(cfg, g)
    key = sha(canonical(fps))
    idx = index(cfg)
    if any(e["input_key"] == key for e in idx):
        return {"mode": "unchanged", "input_key": key, "gathered": g, "fingerprints": fps}
    prev = idx[-1] if idx else None
    prev_fps = load_record(cfg, prev["input_key"])["fingerprints"] if prev else None
    same_core = prev_fps and all(prev_fps[k] == fps[k] for k in ("settings", "senators", "publics", "populations", "bridge"))
    if force_full or not same_core:
        return {"mode": "full", "input_key": key, "previous_key": prev["input_key"] if prev else None, "gathered": g,
                "fingerprints": fps, "committees_recomputed": sorted(fps["committees"])}
    changed = sorted(c for c in set(fps["committees"]) | set(prev_fps["committees"])
                     if fps["committees"].get(c) != prev_fps["committees"].get(c))
    return {"mode": "committees_only", "input_key": key, "previous_key": prev["input_key"], "gathered": g, "fingerprints": fps,
            "committees_recomputed": [c for c in changed if c in fps["committees"]],
            "committees_removed": [c for c in changed if c not in fps["committees"]]}


def compute(cfg: Config = DEFAULT, force_full: bool = False, now: str | None = None) -> dict:
    p = plan(cfg, force_full)
    if p["mode"] == "unchanged":
        return {"mode": "unchanged", "input_key": p["input_key"], "written": False}
    g, key = p["gathered"], p["input_key"]
    if p["mode"] == "full":
        results = _calculate(cfg, g, None)
        computed_in = {"pillar4": key, "pillar5": key, "pillar6": {c: key for c in results["pillar6"]}}
    else:
        prev = load_record(cfg, p["previous_key"])
        fresh = _calculate(cfg, g, set(p["committees_recomputed"]))["pillar6"]
        keep = {c: v for c, v in prev["results"]["pillar6"].items() if c not in p["committees_recomputed"] and c not in p["committees_removed"]}
        results = {"pillar4": prev["results"]["pillar4"], "pillar5": prev["results"]["pillar5"],
                   "pillar6": dict(sorted({**keep, **fresh}.items()))}
        computed_in = {"pillar4": prev["computed_in"]["pillar4"], "pillar5": prev["computed_in"]["pillar5"],
                       "pillar6": {c: (key if c in fresh else prev["computed_in"]["pillar6"][c]) for c in results["pillar6"]}}
    fixture = any(l["content"].get("fixture", False) for k in ("senators", "publics", "populations", "events") for l in g[k])
    record = {"schema": SCHEMA, "input_key": key, "previous_key": p.get("previous_key"), "mode": p["mode"],
              "committees_recomputed": p.get("committees_recomputed", []), "committees_removed": p.get("committees_removed", []),
              "settings": settings(cfg), "versions": versions(cfg, g), "fingerprints": p["fingerprints"], "fixture": fixture,
              "computed_in": computed_in, "results": results}
    body = canonical(record)
    mdir, ip = paths(cfg)
    mdir.mkdir(parents=True, exist_ok=True)
    stamp = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with (mdir / f"{key}.json").open("x") as fh:     # exclusive create: an existing result is never overwritten
            fh.write(body + "\n")
    except FileExistsError:
        raise ComputeError(f"result {key} exists but is not in the index; refusing to overwrite it")
    with ip.open("a") as fh:
        fh.write(canonical({"input_key": key, "previous_key": record["previous_key"], "mode": p["mode"],
                            "measurement_date": record["versions"]["measurement_date"], "computed_at": stamp,
                            "content_sha256": sha(body), "fixture": fixture}) + "\n")
    return {"mode": p["mode"], "input_key": key, "written": True, "committees_recomputed": record["committees_recomputed"]}


def verify(cfg: Config = DEFAULT) -> list[str]:
    """Every indexed record exists, is named by its key, matches its hash, and
    chains to the record before it; the latest record's key equals the key of
    the current inputs (nothing stale); and its results equal a full recompute."""
    problems, prev = [], None
    mdir, _ = paths(cfg)
    idx = index(cfg)
    for i, e in enumerate(idx, 1):
        f = mdir / f"{e['input_key']}.json"
        if not f.exists():
            problems.append(f"index line {i}: {f.name} missing"); continue
        body = f.read_text().rstrip("\n")
        if sha(body) != e["content_sha256"]:
            problems.append(f"index line {i}: {f.name} does not match its recorded hash")
        rec = json.loads(body)
        if rec["input_key"] != e["input_key"] or sha(canonical(rec["fingerprints"])) != e["input_key"]:
            problems.append(f"index line {i}: key does not match the record's inputs")
        if e["previous_key"] != prev:
            problems.append(f"index line {i}: previous_key does not chain")
        prev = e["input_key"]
    if len({e["input_key"] for e in idx}) != len(idx):
        problems.append("a key appears twice in the index")
    unindexed = {f.stem for f in mdir.glob("*.json")} - {e["input_key"] for e in idx} if mdir.exists() else set()
    if unindexed:
        problems.append(f"result files not in the index: {sorted(unindexed)[:3]}")
    if idx and not problems:
        g = gather(cfg)
        fps = fingerprints(cfg, g)
        if sha(canonical(fps)) != idx[-1]["input_key"]:
            problems.append("the latest result was computed from inputs that are no longer current: run compute")
        else:
            latest = load_record(cfg, idx[-1]["input_key"])["results"]
            if json.loads(canonical(_calculate(cfg, g, None))) != latest:
                problems.append("the latest result differs from a full recompute of its inputs")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--full", action="store_true", help="recompute everything even if only committees changed")
    a = ap.parse_args()
    if a.verify:
        probs = verify(DEFAULT)
        print("\n".join(probs) if probs else "Pillars 4-6 results verify.")
        return 1 if probs else 0
    print(json.dumps(compute(DEFAULT, force_full=a.full), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
