"""What's missing, stale or conflicting in the data, in plain words.

    PYTHONPATH=src python -m civicalign.health --report     write the report and the job summary
    PYTHONPATH=src python -m civicalign.health --watch      check the live site

Every item is ok, warn or error. A warn is a known gap that the site already labels. An error
needs someone to look: sources that contradict each other with no official explanation, or a
new drop that was rejected. Neither stops a build, because the gaps are published rather than
hidden; the tests and the supervisor remain the gates that stop publishing.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from . import legislative as L
from . import legislative_sync as SYNC
from . import record_votes as RV
from .config import DEFAULT, Config
from .ideology import ingest as I

DROP_STALE_DAYS = 14
LIVE_STALE_DAYS = 3
LIVE_SITE = "https://safire684-ops.github.io/civicalign/"
LEVELS = {"ok": 0, "warn": 1, "error": 2}


def report_path(cfg: Config = DEFAULT) -> Path:
    return cfg.raw_dir.parent / "processed" / "health.json"


def _read(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def report(cfg: Config = DEFAULT, today: date | None = None) -> dict:
    """Worked out only from saved files, so a build and its recheck see the same answer."""
    snap = I.snapshot(cfg)
    today = today or date.fromisoformat(snap["run_utc"][:10])
    items = []
    def add(level, code, text):
        items.append({"level": level, "code": code, "text": text})

    # the legislative drop
    if not any((p / "MANIFEST.json").exists() for p in L.root(cfg).glob("*")):
        add("error", "drop_missing", "No legislative drop has been imported.")
    else:
        drop = L.load(cfg)
        made = drop["manifest"]["generated_at"][:10]
        age = (today - date.fromisoformat(made)).days
        add("warn" if age > DROP_STALE_DAYS else "ok", "drop_age", f"The legislative files were made {made}, {age} days before this check (limit {DROP_STALE_DAYS}).")
        with cfg.rollcalls_csv.open() as fh:
            have = {v["id"] for v in drop["votes"]}
            missing = sorted(f"{r['congress']}-{r['session']}-{r['clerk_rollnumber']}" for r in L.csv.DictReader(fh)
                             if f"{r['congress']}-{r['session']}-{r['clerk_rollnumber']}" not in have)
        add("warn" if missing else "ok", "drop_coverage", f"{len(missing)} roll calls in Voteview aren't in the legislative files yet, so they have no plain-language explanation." if missing else "Every Voteview roll call is in the legislative files.")
    sync = _read(SYNC.status_path(cfg))
    if sync:
        level = {"imported": "ok", "current": "ok", "not_configured": "warn"}.get(sync["state"], "error")
        add(level, f"drop_sync_{sync['state']}", sync["detail"])

    # the official record
    c = RV.compare(cfg)
    conflict = sorted(k for k, v in c["votes"].items() if v["status"] == "conflict")
    pending = sorted(k for k, v in c["votes"].items() if v["status"] == "pending")
    add("error" if conflict else "ok", "record_conflicts", f"{len(conflict)} roll calls differ from the Congressional Record with no official explanation: {', '.join(conflict[:10])}." if conflict else f"{c['counts']['verified']} roll calls match the Congressional Record.")
    add("warn" if pending else "ok", "record_pending", f"{len(pending)} roll calls haven't been found in the Congressional Record yet: {', '.join(pending[:10])}." if pending else "No roll call is waiting on the Congressional Record.")
    if c["unread_changes"]:
        add("error", "record_notices_unread", f"{len(c['unread_changes'])} change-of-vote notices couldn't be read automatically: {', '.join(c['unread_changes'][:5])}")
    rec = _read(RV.status_path(cfg))
    if rec:
        if rec["state"] != "ok":
            add("warn", "record_unreachable", f"The Congressional Record couldn't be read in this run, so the last saved results are in use. {rec['detail']}")
        if rec.get("pages_changed"):
            add("warn", "record_pages_changed", f"The Congressional Record changed its pages for these roll calls, and they were read again: {', '.join(rec['pages_changed'][:10])}.")
        if rec.get("ahead_of_voteview"):
            add("warn", "voteview_behind", f"{len(rec['ahead_of_voteview'])} roll calls are in the Congressional Record but not in Voteview yet: {', '.join(rec['ahead_of_voteview'][:10])}.")

    # the verified snapshot and the Senate's own site
    old = sorted(s["name"] for s in snap["sources"] if s["checked_utc"][:10] < snap["run_utc"][:10])
    add("warn" if old else "ok", "sources_older", f"These sources couldn't be refreshed in the latest snapshot: {', '.join(old)}." if old else "Every source was checked in the latest snapshot.")
    senate = json.loads((cfg.explain_raw_dir / "senate" / "PROVENANCE.json").read_text())
    stored = sum(1 for r in senate["records"].values())
    pulled = min((r["checked_utc"] for r in senate["records"].values()), default="")[:10]
    add("warn", "senate_blocked", f"senate.gov refuses automated requests, so {stored} passage-vote records are stored copies from {pulled}. The Congressional Record is checked instead.")

    top = max((i["level"] for i in items), key=LEVELS.get, default="ok")
    return {"level": top, "checked": today.isoformat(), "items": items}


def summary(result: dict) -> str:
    marks = {"ok": "OK", "warn": "Attention", "error": "PROBLEM"}
    return "\n".join([f"### Data health: {marks[result['level']]}", "", "| Status | Check |", "|---|---|"] + [f"| {marks[i['level']]} | {i['text']} |" for i in result["items"]]) + "\n"


def _get(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "CivicAlign monitor", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def watch(base: str = LIVE_SITE, today: date | None = None, get=_get) -> list[str]:
    """Problems with the published site. Empty means it's up and recent."""
    today = today or datetime.now(timezone.utc).date()
    problems = []
    def body(path, must):
        status, text = get(base + path)
        if status != 200:
            problems.append(f"/{path} returned {status}.")
        elif must not in text:
            problems.append(f"/{path} doesn't contain {must!r}.")
        return text
    body("", "url=civicalign.html")
    body("senator-check.html", "civicalign.html")
    body("senator-check-original.html", "Where do your senators stand")
    page = body("civicalign.html", 'id="data"')
    m = re.search(r'"snapshot":"(\d{4}-\d{2}-\d{2})"', page)
    if page and not m:
        problems.append("The live page has no snapshot date.")
    elif m and (today - date.fromisoformat(m.group(1))).days > LIVE_STALE_DAYS:
        problems.append(f"The live site's data is from {m.group(1)}, more than {LIVE_STALE_DAYS} days ago, so daily updates may have stopped.")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--watch", action="store_true")
    a = ap.parse_args()
    if a.watch:
        problems = watch()
        print("\n".join(problems) or "The live site is up and recent.")
        return 1 if problems else 0
    result = report(DEFAULT)
    report_path().parent.mkdir(parents=True, exist_ok=True)
    report_path().write_text(json.dumps(result, indent=1) + "\n")
    text = summary(result)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
