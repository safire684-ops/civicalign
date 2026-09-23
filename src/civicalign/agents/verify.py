"""Pre-build consistency checks on the snapshot: the roster, the join keys, the
record counts. Runs every week before the pipeline builds anything, and fails the
run on any problem so the previous verified site stays live.

python -m civicalign.agents.verify
"""
import csv
import json
import sys
import zipfile
from dataclasses import dataclass

from ..config import DEFAULT, Config
from ..sources import rosters, voteview
from .base import load_snapshot


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""

    def line(self) -> str:
        return f"  {'ok  ' if self.ok else 'FAIL'}  {self.name:52s} {self.detail}"


def checks(cfg: Config = DEFAULT) -> list[Check]:
    out: list[Check] = []

    # --- roster: exactly 100 seats, at most two per state --------------------
    roster = rosters.load_current_senators(cfg.roster_json)
    out.append(Check("roster has exactly 100 seated senators", len(roster) == 100, f"{len(roster)}"))
    per_state: dict[str, int] = {}
    for s in roster.values():
        per_state[s.state] = per_state.get(s.state, 0) + 1
    crowded = {k: v for k, v in per_state.items() if v > 2}
    out.append(Check("no state has more than two current senators", not crowded, str(crowded) if crowded else f"{len(per_state)} states"))

    # --- scores join the roster; unscored senators are allowed, invented ones are not
    try:
        scores = voteview.load_scores(cfg.members_csv, cfg.congress, roster, cfg.score_column, cfg.min_roll_calls)
        stray = [b for b in scores if b not in roster]
        out.append(Check("every scored senator is on the current roster", not stray, f"{len(scores)} scored, {100 - len(scores)} awaiting {cfg.min_roll_calls} votes"))
        out.append(Check("a plausible number of senators carry a score", 80 <= len(scores) <= 100, str(len(scores))))
    except Exception as exc:
        out.append(Check("Voteview member file parses and joins the roster", False, f"{type(exc).__name__}: {exc}"))

    # --- committees: membership file joins the roster ------------------------
    try:
        cmtes = rosters.load_senate_committees(cfg.committees_json)
        members = {m.bioguide for ms in cmtes.values() for m in ms}
        unknown = sorted(members - set(roster))
        out.append(Check("Senate committee file has a plausible number of committees", len(cmtes) >= 15, str(len(cmtes))))
        out.append(Check("committee members are on the current roster", len(unknown) <= 5,
                         f"{len(unknown)} listed members not seated: {unknown[:5]}" if unknown else f"{len(members)} members all seated"))
    except Exception as exc:
        out.append(Check("committee membership file parses", False, f"{type(exc).__name__}: {exc}"))

    # --- the survey and population files ------------------------------------
    try:
        rows = [r for r in csv.DictReader(cfg.ideology_tab.open(), delimiter="\t")
                if int(r["presidential_year"]) == cfg.ideology_year]
        out.append(Check(f"survey file has 51 estimates for the {cfg.ideology_year} wave", len(rows) == 51, str(len(rows))))
    except Exception as exc:
        out.append(Check("survey file parses", False, f"{type(exc).__name__}: {exc}"))
    try:
        with cfg.population_csv.open(encoding="latin-1") as fh:
            pops = [r for r in csv.DictReader(fh) if r.get("SUMLEV") == "040"]
        out.append(Check("population file has every state and DC", len(pops) >= 51, str(len(pops))))
    except Exception as exc:
        out.append(Check("population file parses", False, f"{type(exc).__name__}: {exc}"))

    # --- floor votes and bills: sane record counts ---------------------------
    if cfg.rollcalls_csv.exists():
        n_rc = sum(1 for _ in csv.DictReader(cfg.rollcalls_csv.open()))
        out.append(Check("roll-call file has a sane number of votes", n_rc >= 30, str(n_rc)))
    if cfg.billflow_zip.exists():
        try:
            with zipfile.ZipFile(cfg.billflow_zip) as z:
                n_bills = sum(1 for n in z.namelist() if n.endswith(".xml"))
            out.append(Check("bill-status archive has a sane number of bills", n_bills >= 1000, str(n_bills)))
        except zipfile.BadZipFile:
            out.append(Check("bill-status archive is a valid zip", False))

    # --- no source shrank drastically since the last accepted snapshot -------
    snap = load_snapshot(cfg.raw_dir)
    shrunk = [f"{s['name']} {s['previous_bytes']:,}->{s['bytes']:,}" for s in snap.get("sources", [])
              if s.get("previous_bytes") and s.get("bytes", 0) < 0.7 * s["previous_bytes"]]
    out.append(Check("no source shrank by more than 30% since the last snapshot", not shrunk, "; ".join(shrunk)))
    if snap:
        crit = [s for s in snap.get("sources", []) if s.get("critical", True)]
        out.append(Check("last snapshot was accepted with every critical source present",
                         bool(snap.get("accepted")) and all("sha256" in s for s in crit), f"{len(crit)} critical sources"))
    return out


def main() -> int:
    print("Snapshot consistency checks\n")
    results = checks(DEFAULT)
    for c in results:
        print(c.line())
    failed = [c for c in results if not c.ok]
    print()
    if failed:
        print(f"  {len(failed)} check(s) failed: " + "; ".join(c.name for c in failed))
        print("  Nothing is rebuilt or published from this snapshot.")
        return 1
    print(f"  all {len(results)} checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
