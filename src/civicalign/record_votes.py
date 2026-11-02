"""Check every Senate roll call against the official list in the Congressional Record.

    PYTHONPATH=src python -m civicalign.record_votes [--since YYYY-MM-DD]

Voteview supplies the roll calls the site publishes. This adds the Senate's own printed list
of who voted how, and its change-of-vote notices, which Voteview doesn't always pick up. New
results are appended to data/legislative/<congress>/record_votes.jsonl and record_changes.jsonl,
each with the page's address and SHA-256; a stored line is never rewritten. A GovInfo failure
appends nothing and is reported, so votes not yet checked stay marked as not yet checked.

compare() gives each roll call a status:
  verified   the printed list, with any change-of-vote notice applied, explains Voteview's list
  conflict   it doesn't, or the two tallies differ, and nothing official says why
  pending    the Record hasn't been read for this vote yet
"""
import argparse
import csv
import hashlib
import json
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import legislative as L
from .config import DEFAULT, Config
from .sources import congressional_record as CR

NEARBY = (0, -1, 1, -2, -3)      # a late-night vote can be printed in the previous day's issue
RESCAN_DAYS = 10                 # GovInfo can add or correct an issue's metadata for some days
RECHECK = 10                     # stored pages read again each run, in rotation, to catch official corrections
SITEMAP = "https://www.govinfo.gov/sitemap/CREC_{year}_sitemap.xml"


def store_path(cfg: Config = DEFAULT) -> Path:
    return L.root(cfg) / "record_votes.jsonl"


def changes_path(cfg: Config = DEFAULT) -> Path:
    return L.root(cfg) / "record_changes.jsonl"


def status_path(cfg: Config = DEFAULT) -> Path:
    return cfg.raw_dir.parent / "processed" / "record_sync.json"


def cache_dir(cfg: Config = DEFAULT) -> Path:
    return cfg.raw_dir / "congressional_record"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def _append(path: Path, rows: list[dict]) -> None:
    if rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")


def session_of(day: str, cfg: Config = DEFAULT) -> int:
    return int(day[:4]) - (cfg.congress * 2 + 1787) + 1


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).upper()


def voteview(cfg: Config = DEFAULT) -> tuple[dict, dict, dict]:
    """(roll calls by vote id, {vote id: {senator: position}}, {surname: [(state, senator)]})."""
    with cfg.rollcalls_csv.open() as fh:
        rolls = {f"{r['congress']}-{r['session']}-{r['clerk_rollnumber']}": r for r in csv.DictReader(fh)}
    number = {r["rollnumber"]: k for k, r in rolls.items()}
    who, names = {}, {}
    with cfg.members_csv.open() as fh:
        for r in csv.DictReader(fh):
            if r["chamber"] == "Senate" and r["congress"] == str(cfg.congress):
                who[r["icpsr"]] = r["bioguide_id"]
                names.setdefault(_plain(r["bioname"].split(",")[0]), []).append((r["state_abbrev"], r["bioguide_id"]))
    cast: dict[str, dict[str, str]] = {k: {} for k in rolls}
    with cfg.votes_csv.open() as fh:
        for r in csv.DictReader(fh):
            if r["rollnumber"] in number and r["icpsr"] in who:
                cast[number[r["rollnumber"]]][who[r["icpsr"]]] = L.CAST.get(r["cast_code"], "Not Voting")
    return rolls, cast, names


def resolve(name: str, names: dict, serving: set[str] | None = None) -> str | None:
    """A printed surname, such as "Scott (FL)", to a Bioguide id. Two senators can share a
    surname and a state when one succeeded the other, so Voteview's list of who could vote on
    this roll call settles it. Anything still ambiguous returns None."""
    state = None
    if name.endswith(")"):
        name, state = name[:-5], name[-3:-1]
    found = [b for s, b in names.get(_plain(name), []) if state is None or s == state]
    if len(found) > 1 and serving is not None:
        found = [b for b in found if b in serving]
    return found[0] if len(found) == 1 else None


def _issue(day: str, cfg: Config, today: date, seen: dict) -> dict | None:
    if day not in seen:
        recent = date.fromisoformat(day) >= today - timedelta(days=RESCAN_DAYS)
        mods = CR.fetch(CR.issue_url(day), None if recent else cache_dir(cfg) / day / "mods.xml")
        seen[day] = {**CR.issue_index(mods), "date": day} if mods is not None else None
    return seen[day]


def _page(granule: str, day: str, cfg: Config) -> bytes | None:
    return CR.fetch(CR.page_url(granule), cache_dir(cfg) / day / f"{granule}.htm")


def find_roll(number: int, day: str, cfg: Config, today: date, seen: dict) -> tuple[dict, str, str, bytes] | None:
    """(parsed roll, issue date, granule, page bytes), or None if it isn't in the Record yet."""
    issues = [i for off in NEARBY if (i := _issue((date.fromisoformat(day) + timedelta(days=off)).isoformat(), cfg, today, seen))]
    for i in issues:
        if number in i["votes"]:
            page = _page(i["votes"][number], i["date"], cfg)
            roll = CR.parse_rolls(page).get(number) if page else None
            if roll:
                return roll, i["date"], i["votes"][number], page
    # The metadata sometimes omits a vote. Read the issue's other Senate pages, nearest day first.
    for i in issues:
        for g in dict.fromkeys(list(i["votes"].values()) + i["senate"]):
            page = _page(g, i["date"], cfg)
            roll = CR.parse_rolls(page).get(number) if page else None
            if roll:
                return roll, i["date"], g, page
    return None


def record_line(vote_id: str, roll: dict, issue_day: str, granule: str, page: bytes, names: dict, serving: set[str], when: str) -> dict:
    line = {"id": vote_id, "issue": issue_day, "granule": granule, "url": CR.page_url(granule), "sha256": hashlib.sha256(page).hexdigest(),
            "retrieved_utc": when, "kind": roll["kind"], "announced": roll["announced"], "complete": roll["complete"], "unknown": []}
    for position, printed in roll["lists"].items():
        ids = []
        for name in printed:
            who = resolve(name, names, serving)
            ids.append(who) if who else line["unknown"].append(name)
        line[position] = sorted(ids)
    return line


def issue_dates(start: str, today: date) -> list[str]:
    """Every issue GovInfo lists from start through today."""
    days = set()
    for year in range(int(start[:4]), today.year + 1):
        body = CR.fetch(SITEMAP.format(year=year))
        for node in ET.fromstring(body).iter() if body else ():
            if node.tag.endswith("loc") and "/CREC-" in (node.text or ""):
                days.add(node.text.strip().rsplit("CREC-", 1)[1][:10])
    return sorted(d for d in days if d >= start)


def recheck(stored: dict, rolls: dict, cast: dict, names: dict, cfg: Config, today: date, when: str, new_lines: list[dict]) -> list[str]:
    """Read some stored pages again: every vote the legislative files don't have, plus a rotating
    sample of the rest. A page the Record has since corrected gets a new line; the old one stays."""
    have = {v["id"] for v in L.load(cfg)["votes"]}
    ids = sorted(stored)
    start = (today.toordinal() * RECHECK) % max(len(ids), 1)
    sample = set((ids + ids)[start:start + RECHECK]) | {k for k in ids if k not in have}
    changed = []
    for vote_id in sorted(sample):
        old = stored[vote_id]
        path = cache_dir(cfg) / old["issue"] / f"{old['granule']}.htm"
        page = CR.fetch(old["url"])
        if page is None:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(page)
        if hashlib.sha256(page).hexdigest() == old["sha256"]:
            continue
        roll = CR.parse_rolls(page).get(int(vote_id.split("-")[2]))
        if roll and vote_id in rolls:
            new_lines.append(record_line(vote_id, roll, old["issue"], old["granule"], page, names, set(cast[vote_id]), when))
            changed.append(vote_id)
    return changed


def update(cfg: Config = DEFAULT, today: date | None = None, since: str | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rolls, cast, names = voteview(cfg)
    stored = {r["id"]: r for r in read_jsonl(store_path(cfg))}
    known_changes = {r["granule"] for r in read_jsonl(changes_path(cfg))}
    seen, new_lines, new_changes = {}, [], []
    result = {"checked_utc": when, "state": "ok", "detail": ""}
    try:
        for vote_id, r in sorted(rolls.items(), key=lambda x: (x[1]["date"], int(x[1]["clerk_rollnumber"]))):
            if vote_id in stored and stored[vote_id]["complete"] and not stored[vote_id]["unknown"]:
                continue
            found = find_roll(int(r["clerk_rollnumber"]), r["date"], cfg, today, seen)
            if found:
                line = record_line(vote_id, *found[:3], found[3], names, set(cast[vote_id]), when)
                if vote_id not in stored or stored[vote_id]["sha256"] != line["sha256"]:
                    new_lines.append(line)
        result["pages_changed"] = recheck(stored, rolls, cast, names, cfg, today, when, new_lines)
        first = since or (max((r["issue"] for r in stored.values()), default=min(r["date"] for r in rolls.values())))
        start = min(first, (today - timedelta(days=RESCAN_DAYS)).isoformat()) if since is None else first
        days = issue_dates(start, today)
        ahead = []
        for day in days:
            issue = _issue(day, cfg, today, seen)
            if not issue:
                continue
            session = session_of(day, cfg)
            ahead += [f"{cfg.congress}-{session}-{n}" for n in issue["votes"] if f"{cfg.congress}-{session}-{n}" not in rolls]
            for g in issue["changes"]:
                if g in known_changes:
                    continue
                page = _page(g, day, cfg)
                if page is None:
                    continue
                notice = CR.parse_changes(page)
                base = {"granule": g, "issue": day, "url": CR.page_url(g), "sha256": hashlib.sha256(page).hexdigest(), "retrieved_utc": when, "granted": notice["granted"]}
                if not notice["found"]:
                    new_changes.append({**base, "unread": True})
                for n in notice["found"]:
                    vote_id = f"{cfg.congress}-{session}-{n['number']}"
                    new_changes.append({**base, "id": vote_id, "senator": resolve(n["speaker"].title(), names, set(cast.get(vote_id, {}))), "speaker": n["speaker"], "to": n["to"]})
        result.update(issues_through=days[-1] if days else None, ahead_of_voteview=sorted(set(ahead)))
    except (CR.RecordError, ET.ParseError, OSError) as e:
        result.update(state="unreachable", detail=f"{type(e).__name__}: {e}"[:300])
    _append(store_path(cfg), new_lines)
    _append(changes_path(cfg), new_changes)
    result.update(new_votes=len(new_lines), new_changes=len(new_changes))
    return result


def latest_records(cfg: Config = DEFAULT) -> dict[str, dict]:
    return {r["id"]: r for r in read_jsonl(store_path(cfg))}


def compare(cfg: Config = DEFAULT) -> dict:
    """Each Voteview roll call against the Record. Nothing here changes what's published."""
    rolls, cast, _ = voteview(cfg)
    records = latest_records(cfg)
    changes: dict[str, list[dict]] = {}
    unread = []
    for c in read_jsonl(changes_path(cfg)):
        if c.get("unread") or not c.get("senator") or not c.get("granted"):
            unread.append(c["url"])
        else:
            changes.setdefault(c["id"], []).append(c)
    votes = {}
    for vote_id, r in rolls.items():
        rec = records.get(vote_id)
        if rec is None or not rec["complete"] or rec["unknown"]:
            votes[vote_id] = {"status": "pending"}
            continue
        printed = {s: p for p in ("Yea", "Nay", "Present", "Not Voting") for s in rec.get(p, [])}
        final = {**printed, **{c["senator"]: c["to"] for c in changes.get(vote_id, [])}}
        here = cast[vote_id]
        def differs(a, b):
            return [s for s in sorted(set(a) | set(b)) if a.get(s, "Not Voting") != b.get(s, "Not Voting")]
        as_printed, as_corrected = differs(printed, here), differs(final, here)
        tally = (len(rec.get("Yea", [])), len(rec.get("Nay", [])))
        ok = (int(r["yea_count"]), int(r["nay_count"])) == tally
        explained = not as_printed or not as_corrected or set(as_corrected) <= {c["senator"] for c in changes.get(vote_id, [])}
        votes[vote_id] = {"status": "verified" if ok and explained else "conflict", "url": rec["url"], "issue": rec["issue"], "granule": rec["granule"],
                          "differs": sorted(set(as_printed) | set(as_corrected)), "printed_tally": {"yea": tally[0], "nay": tally[1]},
                          "final": final, "changes": [{"senator": c["senator"], "to": c["to"], "url": c["url"], "issue": c["issue"]} for c in changes.get(vote_id, [])]}
    counts = {s: sum(1 for v in votes.values() if v["status"] == s) for s in ("verified", "conflict", "pending")}
    return {"votes": votes, "counts": counts, "unread_changes": unread}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", help="scan every issue from this date for change-of-vote notices")
    a = ap.parse_args()
    result = update(DEFAULT, since=a.since)
    status_path().parent.mkdir(parents=True, exist_ok=True)
    status_path().write_text(json.dumps(result, indent=1) + "\n")
    c = compare(DEFAULT)
    print(f"Congressional Record: {result['state']} {result['detail']} new votes {result['new_votes']}, new notices {result['new_changes']}; {c['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
