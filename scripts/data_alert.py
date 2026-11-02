"""Keep one open GitHub issue while the daily update or the data needs attention.

    python scripts/data_alert.py --job-status success
    python scripts/data_alert.py --watch-failed "what went wrong"

Opens or updates one issue, found by its title, when the job failed or the health report has an
error, and closes it once a later run is clean. Needs GH_TOKEN, GITHUB_REPOSITORY and, for the
link, RUN_URL. It reports only and has no effect on what gets published.
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

TITLE = "CivicAlign data alert"
HEALTH = Path(__file__).resolve().parent.parent / "data" / "processed" / "health.json"


def problems(job_status: str, health: dict | None) -> list[str]:
    out = []
    if job_status != "success":
        out.append(f"The daily update ended with status: {job_status}. The last verified site is still published.")
    out += [i["text"] for i in (health or {}).get("items", []) if i["level"] == "error"]
    return out


def body(found: list[str], run_url: str) -> str:
    return "\n".join(f"- {p}" for p in found) + (f"\n\nRun: {run_url}" if run_url else "") + "\n\nThis issue closes itself after a clean run."


def api(path: str, method: str = "GET", payload: dict | None = None):
    request = urllib.request.Request(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}", method=method,
                                     data=json.dumps(payload).encode() if payload is not None else None,
                                     headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json", "User-Agent": "CivicAlign monitor"})
    with urllib.request.urlopen(request, timeout=60) as r:
        return json.loads(r.read() or "null")


def apply(found: list[str], run_url: str, call=api) -> str:
    """"opened", "updated", "closed" or "nothing"."""
    existing = [i for i in call("issues?state=open&per_page=100") if i["title"] == TITLE and "pull_request" not in i]
    if found:
        if existing:
            call(f"issues/{existing[0]['number']}", "PATCH", {"body": body(found, run_url)})
            return "updated"
        call("issues", "POST", {"title": TITLE, "body": body(found, run_url)})
        return "opened"
    for issue in existing:
        call(f"issues/{issue['number']}", "PATCH", {"state": "closed"})
    return "closed" if existing else "nothing"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job-status", default="success")
    ap.add_argument("--watch-failed", default="")
    a = ap.parse_args()
    if a.watch_failed:
        found = [a.watch_failed]
    else:
        health = json.loads(HEALTH.read_text()) if HEALTH.exists() else None
        found = problems(a.job_status, health)
    print("data alert:", apply(found, os.environ.get("RUN_URL", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
