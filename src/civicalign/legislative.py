"""The legislative data drop: floor votes, positions, bills, committee votes and nominations.

    PYTHONPATH=src python -m civicalign.legislative import <folder>

A drop is a folder of JSON files made by the 50degrees pipeline (`civicalign export 119`).
It is imported byte for byte into data/legislative/<congress>/<date>/ with a MANIFEST.json
of each file's SHA-256, and load() refuses any file that no longer matches. Nothing here
changes or recalculates Engine B: the two systems meet only through shared ids (senator
Bioguide id, vote id, bill id, nomination id), and problems() lists any id that fails to join.

vote_division(): the one thing calculated from a drop. For a roll call, the senators with a
negative nominate_dim1 and those with a positive one are counted separately. If a strict
majority of one group voted Yea and a strict majority of the other voted Nay, the vote divided
the two sides of the Voteview scale, and each answer is labelled with the side that mostly gave
it. Any other vote is not labelled. This describes how senators voted, never what the measure
is, and no number is derived from it for any senator or issue. Rule vote_division_v1.
"""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import DEFAULT, Config

FILES = ("meta.json", "senators.json", "votes.json", "positions.json", "bills.json", "committee_votes.json", "nominations.json", "README.md")
DIVISION_RULE = "vote_division_v1"
DIVISION_TEXT = ("Senators with a negative and with a positive Voteview score are counted separately. If a strict majority of one "
                 "group voted Yes and a strict majority of the other voted No, each answer is labelled with the side that mostly "
                 "gave it. Other votes are not labelled. It describes how senators voted, not the content of the measure.")


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


def vote_division(positions: dict[str, str], scores: dict[str, float]) -> str | None:
    """"yes_liberal" / "yes_conservative" for a roll call that divided the two sides, else None."""
    count = {"lib": {"Yea": 0, "Nay": 0}, "con": {"Yea": 0, "Nay": 0}}
    for sid, pos in positions.items():
        s = scores.get(sid)
        if s is None or s == 0 or pos not in ("Yea", "Nay"):
            continue
        count["lib" if s < 0 else "con"][pos] += 1
    # strict majority of those voting Yea or Nay in each group
    lib, con = count["lib"], count["con"]
    if lib["Yea"] > lib["Nay"] and con["Nay"] > con["Yea"]:
        return "yes_liberal"
    if lib["Nay"] > lib["Yea"] and con["Yea"] > con["Nay"]:
        return "yes_conservative"
    return None


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "import":
        print(import_drop(Path(sys.argv[2])))
    else:
        sys.exit(__doc__)
