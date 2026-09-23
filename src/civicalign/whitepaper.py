"""Refresh the figures WHITEPAPER.md quotes, from a fresh pipeline run.

The whitepaper is hand-written prose; only its numbers and tables are generated.
Run after the weekly data changes:  PYTHONPATH=src python -m civicalign.whitepaper
The weekly job warns (never blocks) when the prose is stale; this script is how a
person brings it back into line in one command.
"""
import re
import statistics as st
import sys
from pathlib import Path

from .build_demo import COMMITTEE_NAMES, NUMBER_WORDS
from .config import DEFAULT
from .pipeline import Report, run

DOC = Path(__file__).resolve().parents[2] / "WHITEPAPER.md"


def _s(v: float, places: int = 3) -> str:
    """Signed, with the document's typographic minus."""
    return f"{v:+.{places}f}".replace("-", "−")


def _table(text: str, header_prefix: str, rows: list[str]) -> str:
    """Replace the body rows of the markdown table whose header starts with header_prefix."""
    lines = text.split("\n")
    i = next(k for k, ln in enumerate(lines) if ln.startswith(header_prefix))
    j = i + 2  # header, separator
    while j < len(lines) and lines[j].startswith("|"):
        j += 1
    return "\n".join(lines[:i + 2] + rows + lines[j:])


def refresh(text: str, r: Report) -> str:
    ch = r.chamber
    dem = st.median(v for b, v in r.scores.items() if r.senators[b].party == "Democrat")
    rep = st.median(v for b, v in r.scores.items() if r.senators[b].party == "Republican")
    text = re.sub(r"the middle Democrat \([−+-]?\d\.\d{3}\)", f"the middle Democrat ({_s(dem)})", text)
    text = re.sub(r"middle\nRepublican \([−+-]?\d\.\d{3}\)", f"middle\nRepublican ({_s(rep)})", text)
    text = re.sub(r"against the Senate's middle \([−+-]?\d\.\d{3}\)", f"against the Senate's middle ({_s(ch.median)})", text)

    top = sorted(r.committees, key=lambda c: -abs(c.median - ch.median))[:6]
    text = _table(text, "| committee | members' midpoint | vs. Senate |",
                  [f"| {COMMITTEE_NAMES.get(c.code, c.code)} | {_s(c.median)} | {_s(c.median - ch.median)} | {c.stability.worst_shift:.2f} |"
                   for c in top])
    oi = [o for o in r.output_ideology if o.is_reportable]
    text = _table(text, "| committee | floor votes | where they divided the Senate |",
                  [f"| {COMMITTEE_NAMES.get(o.code, o.code)} | {o.n_votes} | {_s(o.coi)} | {_s(o.vs_senate)} |" for o in oi])
    text = re.sub(r"Only \w+ committees have seven or more",
                  f"Only {NUMBER_WORDS[len(oi)].lower()} committees have seven or more", text)

    ref = sum(g.referred for g in r.gatekeeping)
    fi = next(g for g in r.gatekeeping if g.code == "SSFI")
    text = re.sub(r"of [\d,]+ distinct bills sent to a Senate committee\s+\([\d,]+\s+referrals, since some bills go to two committees\), \d+ have been sent on to\s+the floor\. The Finance Committee has sent on \d+ of \d+\.",
                  f"of {r.bills_referred_unique:,} distinct bills sent to a Senate committee\n({ref:,} referrals, since some bills go to two committees), {r.bills_reported_unique} have been sent on to\nthe floor. The Finance Committee has sent on {fi.reported} of {fi.referred}.", text)
    text = re.sub(r"get through [\d.]+ percentage\npoints more often", f"get through {r.gatekeeping_baseline:.1f} percentage\npoints more often", text)
    rows = [g for g in r.gatekeeping if g.is_reportable]
    rows.sort(key=lambda g: -abs(g.gbi_vs_baseline))
    text = _table(text, "| committee | liberal-record sponsors: sent forward |",
                  [f"| {COMMITTEE_NAMES.get(g.code, g.code)} | {g.lib_reported} of {g.lib_referred} | {g.con_reported} of {g.con_referred} | {_s(g.gbi_vs_baseline, 1)} |"
                   for g in rows[:4]])
    n = len([g for g in r.gatekeeping if g.is_reportable])
    text = re.sub(r"bill moves the rate by several points\. \w+ committees have enough\.",
                  f"bill moves the rate by several points. {NUMBER_WORDS[n] if n < len(NUMBER_WORDS) else n} committees have enough.", text)

    usable = sum(1 for c in r.committees if not c.is_noise)
    text = re.sub(r"\*\*\d+ of \d+\*\* committees", f"**{usable} of {len(r.committees)}** committees", text)
    gaps = {}
    for code, label in (("SSEG", "Energy"), ("SSBU", "Budget"), ("SSCM", "Commerce")):
        cs = next(c for c in r.committees if c.code == code)
        gaps[label] = cs.chair_coord - cs.majority_median
    text = re.sub(r"Energy [−+-]?\d\.\d{3},\nBudget [−+-]?\d\.\d{3}, Commerce [−+-]?\d\.\d{3}\.",
                  f"Energy {_s(gaps['Energy'])},\nBudget {_s(gaps['Budget'])}, Commerce {_s(gaps['Commerce'])}.", text)
    return text


def main() -> int:
    r = run(DEFAULT)
    before = DOC.read_text()
    after = refresh(before, r)
    if after != before:
        DOC.write_text(after)
        print("WHITEPAPER.md figures refreshed.")
    else:
        print("WHITEPAPER.md already current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
