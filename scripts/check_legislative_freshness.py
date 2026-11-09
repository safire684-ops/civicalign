"""Non-blocking status for the separately imported legislative export.

Run after the verified source fetch. A stale drop is never presented as fresh;
this report does not import or approve data and does not change publish gates.
"""
import argparse
import csv
import json
import os
from datetime import date
from pathlib import Path


def audit(root: Path, today: date, max_age_days: int = 14) -> tuple[str, bool]:
    base = root / "data" / "legislative" / "119"
    drops = sorted(p for p in base.iterdir() if (p / "MANIFEST.json").is_file()) if base.exists() else []
    if not drops:
        return "Legislative export: MISSING — no imported 50degrees drop.", True
    d = drops[-1]
    meta = json.loads((d / "meta.json").read_text())
    imported = date.fromisoformat(meta["generated_at"][:10])
    age = (today - imported).days
    votes = json.loads((d / "votes.json").read_text())
    drop_ids = {v["id"] for v in votes}
    last_vote = max((v["date"] for v in votes), default="none")
    rollcalls = root / "data" / "raw" / "S119_rollcalls.csv"
    missing = []
    if rollcalls.exists():
        with rollcalls.open(newline="") as fh:
            reader = csv.DictReader(fh)
            required = {"congress", "session", "clerk_rollnumber"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                return "Legislative export: SOURCE GAP — Voteview rollcall schema not readable.", True
            for v in reader:
                if v["congress"] == "119":
                    vid = f'{v["congress"]}-{v["session"]}-{v["clerk_rollnumber"]}'
                    if vid not in drop_ids:
                        missing.append(vid)
    else:
        return "Legislative export: SOURCE GAP — Voteview snapshot unavailable for coverage comparison.", True
    stale = age > max_age_days or bool(missing)
    status = "NEEDS ATTENTION" if stale else "COVERAGE OK"
    lines = [
        f"Legislative export: {status}",
        f"50degrees generated: {imported.isoformat()} ({age} days old; threshold {max_age_days})",
        f"Last included roll call: {last_vote}",
        f"Roll calls in verified Voteview snapshot but missing from export: {len(missing)}",
        "This status does not verify individual vote correctness or indicate automatic import.",
    ]
    if missing:
        lines.append("Missing vote IDs: " + ", ".join(sorted(missing)))
    return "\n".join(lines), stale


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--max-age-days", type=int, default=14)
    args = parser.parse_args()
    report, needs_attention = audit(args.root, args.today, args.max_age_days)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as fh:
            fh.write("### Legislative export freshness\n\n")
            fh.write("\n\n".join(line for line in report.splitlines()))
            fh.write("\n\n")
    # Warn instead of failing the established site pipeline while the external
    # export is still manually produced. This is a visibility check, not approval.
    if needs_attention:
        print("::warning title=Legislative export coverage::Imported legislative data needs review.")


if __name__ == "__main__":
    main()
