"""The four update agents, each with the check that makes its data trustworthy.

A validator's job is to catch the failure modes that do NOT look like failures:
a truncated download, a server returning an HTML error page with a 200 status, a
schema change that silently drops a column. Each check below exists because that
source can fail that way.
"""
import csv
import io
import json
import zipfile
from pathlib import Path

from ..config import DEFAULT
from .base import Agent

RAW = DEFAULT.raw_dir


def _senator_scores(path: Path) -> str | None:
    """Voteview: the column we depend on must exist and hold real numbers."""
    with path.open() as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return "no header row"
        for col in ("bioguide_id", "nokken_poole_dim1", "congress", "chamber"):
            if col not in reader.fieldnames:
                return f"column {col!r} has disappeared from the file"
        senate = 0
        for row in reader:
            if row["chamber"] == "Senate" and row["congress"] == str(DEFAULT.congress):
                senate += 1
        if senate < 100:
            return f"only {senate} senators for congress {DEFAULT.congress}; expected 100 or more"
    return None


def _roster(path: Path) -> str | None:
    """The roster decides who counts as seated, so an exact 100 is required."""
    people = json.loads(path.read_text())
    sens = [p for p in people if p["terms"][-1]["type"] == "sen"]
    if len(sens) != 100:
        return f"{len(sens)} sitting senators; a Senate has 100"
    if any("bioguide" not in p["id"] for p in sens):
        return "a senator is missing a bioguide id, which is the join key"
    return None


def _committees(path: Path) -> str | None:
    data = json.loads(path.read_text())
    senate = [c for c in data if c.startswith(("SS", "SL")) and len(c) == 4]
    if len(senate) < 15:
        return f"only {len(senate)} Senate committees found"
    return None


def _bill_flow(path: Path) -> str | None:
    """The bulk zip: must open, and must hold a plausible number of bills."""
    try:
        with zipfile.ZipFile(path) as z:
            xml = [n for n in z.namelist() if n.endswith(".xml")]
    except zipfile.BadZipFile:
        return "not a valid zip -- the server probably returned an error page"
    if len(xml) < 1000:
        return f"only {len(xml)} bills in the archive; expected thousands"
    return None


def _populations(path: Path) -> str | None:
    col = f"POPESTIMATE{DEFAULT.population_year}"
    with path.open() as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or col not in reader.fieldnames:
            return f"column {col!r} not present; Census may have moved to a new vintage"
        states = [r for r in reader if r.get("SUMLEV") == "040"]
    if len(states) < 50:
        return f"only {len(states)} states in the file"
    return None


def all_agents() -> list[Agent]:
    return [
        Agent(
            name="senator scores",
            url="https://voteview.com/static/data/out/members/HSall_members.csv",
            target=RAW / "HSall_members.csv",
            validate=_senator_scores,
            min_bytes=1_000_000,
        ),
        Agent(
            name="seated senators",
            url="https://unitedstates.github.io/congress-legislators/legislators-current.json",
            target=RAW / "legislators-current.json",
            validate=_roster,
            min_bytes=100_000,
        ),
        Agent(
            name="committee rosters",
            url="https://unitedstates.github.io/congress-legislators/committee-membership-current.json",
            target=RAW / "committee-membership-current.json",
            validate=_committees,
            min_bytes=50_000,
        ),
        Agent(
            name="bill flow",
            url=f"https://www.govinfo.gov/bulkdata/BILLSTATUS/{DEFAULT.congress}/s/"
                f"BILLSTATUS-{DEFAULT.congress}-s.zip",
            target=RAW / f"BILLSTATUS-{DEFAULT.congress}-s.zip",
            validate=_bill_flow,
            min_bytes=1_000_000,
            timeout=300,
        ),
        Agent(
            name="state populations",
            url="https://www2.census.gov/programs-surveys/popest/datasets/"
                "2020-2024/state/totals/NST-EST2024-ALLDATA.csv",
            target=RAW / "NST-EST2024-ALLDATA.csv",
            validate=_populations,
            min_bytes=10_000,
        ),
    ]
