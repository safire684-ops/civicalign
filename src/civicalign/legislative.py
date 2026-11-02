"""The legislative data drop: floor votes, positions, bills, committee votes and nominations.

    PYTHONPATH=src python -m civicalign.legislative import <folder>

A drop is a folder of JSON files made by the 50degrees pipeline (`civicalign export 119`).
It is imported byte for byte into data/legislative/<congress>/<date>/ with a MANIFEST.json
of each file's SHA-256, and load() refuses any file that no longer matches. Nothing here
changes or recalculates Engine B: the two systems meet only through shared ids (senator
Bioguide id, vote id, bill id, nomination id), and problems() lists any id that fails to join.

Two things are worked out from a drop, and neither is a score for anyone:

vote_evidence() sorts a roll call by what kind of evidence it is (rule issue_votes_v1):
"direct" is a Yes or No on a measure itself (passage, an amendment, accepting the other
chamber's version); "procedural" is a step such as ending debate or tabling; "nomination" is
a vote on a person, not a policy stance; "insufficient" has no usable plain-language meaning.

party_majorities() says whether most Democrats and most Republicans who voted Yes or No
landed on opposite sides of a roll call (rule party_majorities_v1). It describes the Senate's
votes as a whole and is never applied to a senator.

reconcile() compares the drop with Voteview's raw roll calls in the current snapshot, so that
a disagreement or a gap between the two systems is published instead of hidden.
"""
import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import DEFAULT, Config

FILES = ("meta.json", "senators.json", "votes.json", "positions.json", "bills.json", "committee_votes.json", "nominations.json", "README.md")
EVIDENCE_RULE = "issue_votes_v1"
EVIDENCE_TEXT = ("Votes are grouped by the official policy area of the bill they belong to. A direct vote is a Yes or No on the measure itself: "
                 "passage, an amendment, or accepting the other chamber's version. Other votes are procedural steps, listed separately because "
                 "they don't by themselves show a position on the measure. Votes on nominations are kept apart, because they are about a person. "
                 "If a senator has no direct Yes or No in an area, or a vote has no plain-language meaning, the page says Insufficient evidence. "
                 "No score or liberal or conservative label is worked out from these votes.")
PARTY_RULE = "party_majorities_v1"
PARTY_TEXT = ("Among Democrats and among Republicans who voted Yes or No, a roll call counts as opposed when a strict majority of one party voted Yes "
              "and a strict majority of the other voted No. It describes roll calls across the Senate and is never applied to a single senator.")
DIRECT = {"passage", "amendment", "motion_to_concur"}
CAST = {"1": "Yea", "2": "Yea", "3": "Yea", "4": "Nay", "5": "Nay", "6": "Nay", "7": "Present", "8": "Present", "9": "Not Voting"}


class LegislativeError(RuntimeError):
    pass


def root(cfg: Config = DEFAULT) -> Path:
    return cfg.ideology_dir.parent / "legislative" / str(cfg.congress)


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_dir(cfg: Config = DEFAULT) -> Path:
    drops = sorted(p for p in root(cfg).glob("*") if (p / "MANIFEST.json").exists())
    if not drops:
        raise LegislativeError(f"no legislative drop under {root(cfg)}: run python -m civicalign.legislative import <folder>")
    return drops[-1]


def import_drop(folder: Path, cfg: Config = DEFAULT) -> Path:
    """Copy a drop byte for byte. An existing drop is never overwritten."""
    meta = json.loads((folder / "meta.json").read_text())
    if meta["congress"] != cfg.congress:
        raise LegislativeError(f"drop is for Congress {meta['congress']}, this build is {cfg.congress}")
    dest = root(cfg) / meta["generated_at"][:10]
    if dest.exists():
        raise LegislativeError(f"{dest} already exists: a drop is never overwritten")
    dest.mkdir(parents=True)
    for name in FILES:
        shutil.copyfile(folder / name, dest / name)
    manifest = {"congress": cfg.congress, "generated_at": meta["generated_at"], "imported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "files": {name: sha_file(dest / name) for name in FILES}}
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return dest


def load(cfg: Config = DEFAULT) -> dict:
    """The latest drop, after checking every file against its manifest."""
    d = latest_dir(cfg)
    manifest = json.loads((d / "MANIFEST.json").read_text())
    for name, want in manifest["files"].items():
        if sha_file(d / name) != want:
            raise LegislativeError(f"{d / name} does not match its manifest")
    out = {n[:-5]: json.loads((d / n).read_text()) for n in FILES if n.endswith(".json")}
    out["manifest"], out["dir"] = manifest, d
    return out


def problems(drop: dict, engine_ids: set[str]) -> list[str]:
    """Every id that fails to join, within the drop and against Engine B's senators."""
    out = []
    senators = {s["id"] for s in drop["senators"]}
    votes = {v["id"]: v for v in drop["votes"]}
    bills = {b["id"] for b in drop["bills"]}
    noms = {n["id"] for n in drop["nominations"]}
    if set(drop["positions"]) != set(votes):
        out.append("positions and votes cover different roll calls")
    voters = {i for m in drop["positions"].values() for i in m}
    out += [f"position by unknown senator {i}" for i in sorted(voters - senators)]
    out += [f"senator {i} is not in Engine B's senator table" for i in sorted(senators - engine_ids)]
    out += [f"vote {v['id']} names unknown bill {v['bill']}" for v in drop["votes"] if v["bill"] and v["bill"] not in bills]
    for b in drop["bills"]:
        out += [f"bill {b['id']} names unknown vote {x}" for x in b["votes"] if x not in votes]
    for n in drop["nominations"]:
        out += [f"nomination {n['id']} names unknown vote {x}" for x in n["votes"] if x not in votes]
    for v in drop["votes"]:
        out += [f"vote {v['id']} names unknown nomination {x}" for x in v["nominations"] if x not in noms]
    return out


def vote_evidence(vote: dict) -> str:
    m = vote.get("meaning")
    if not m or not m.get("yes_means") or not m.get("no_means") or m.get("outcome_kind") == "unexplained":
        return "insufficient"
    if vote["measure_type"] == "nomination":
        return "nomination"
    return "direct" if vote["question_type"] in DIRECT else "procedural"


def party_majorities(by_party: dict) -> str:
    """"opposed" / "together" / "no_majority" (a tie, or a party with no Yes or No votes)."""
    leans = []
    for party in ("D", "R"):
        c = by_party.get(party, {})
        yes, no = c.get("Yea", 0), c.get("Nay", 0)
        leans.append(None if yes == no else yes > no)
    if None in leans:
        return "no_majority"
    return "opposed" if leans[0] != leans[1] else "together"


def reconcile(drop: dict, cfg: Config = DEFAULT) -> dict:
    """The drop against Voteview's raw roll calls in the current snapshot."""
    rows = {}
    with cfg.rollcalls_csv.open() as fh:
        for r in csv.DictReader(fh):
            rows[f"{r['congress']}-{r['session']}-{r['clerk_rollnumber']}"] = r
    icpsr = {}
    with cfg.members_csv.open() as fh:
        for r in csv.DictReader(fh):
            if r["chamber"] == "Senate" and r["congress"] == str(cfg.congress):
                icpsr[r["icpsr"]] = r["bioguide_id"]
    cast: dict[str, dict[str, str]] = {}
    with cfg.votes_csv.open() as fh:
        for r in csv.DictReader(fh):
            if r["icpsr"] in icpsr:
                cast.setdefault(r["rollnumber"], {})[icpsr[r["icpsr"]]] = CAST.get(r["cast_code"], "Not Voting")
    tallies, positions, compared = {}, {}, 0
    for v in drop["votes"]:
        r = rows.get(v["id"])
        if r is None:
            continue
        if (int(r["yea_count"]), int(r["nay_count"])) != (v["counts"]["yea"], v["counts"]["nay"]):
            tallies[v["id"]] = {"yea": int(r["yea_count"]), "nay": int(r["nay_count"])}
        here = drop["positions"][v["id"]]
        for sid, pos in cast.get(r["rollnumber"], {}).items():
            compared += 1
            if here.get(sid, "Not Voting") != pos:
                positions.setdefault(v["id"], []).append({"id": sid, "here": here.get(sid, "Not Voting"), "voteview": pos})
    newer = sorted(r["date"] for k, r in rows.items() if k not in {v["id"] for v in drop["votes"]})
    return {"shared": sum(1 for v in drop["votes"] if v["id"] in rows), "positions_compared": compared, "tallies": tallies, "positions": positions,
            "only_in_drop": sorted(v["id"] for v in drop["votes"] if v["id"] not in rows), "newer_count": len(newer), "newer_through": newer[-1] if newer else None}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "import":
        print(import_drop(Path(sys.argv[2])))
    else:
        sys.exit(__doc__)
