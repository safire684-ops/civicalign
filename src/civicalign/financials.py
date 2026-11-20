"""Weekly no-key, source-attributed Senate financial disclosure snapshots.

The figures come from the public Senate Files index and senator pages, which
transcribe official Senate eFD annual reports. Values are *estimated intervals*
rather than actual wealth. This optional feed must never break verified voting
updates. No credentials, browser sessions, payment, LLM or member rankings.
"""
import argparse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from .config import DEFAULT

BASE = "https://senatefiles.org"
OFFICIAL = "https://efdsearch.senate.gov/search/"
MIN_COVERAGE = 70
MAX_HTML = 8_000_000
FRESH_DAYS = 7
ID_RE = re.compile(r"/senator/([A-Z]\d{6})(?:[/?#]|$)")
YEAR_RE = re.compile(r"^20\d\d$")
VALUE_RE = re.compile(r"^[−-]?\$[\d,.]+[KMB]?\s*[–-]\s*[−-]?\$[\d,.]+[KMB]?\+?$")


class Tables(HTMLParser):
    """Collect table text and link targets using only Python stdlib."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.depth = 0
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.table = []
        elif self.depth == 1 and tag == "tr":
            self.row = []
        elif self.depth == 1 and tag in ("td", "th") and self.row is not None:
            self.cell = {"parts": [], "url": ""}
        elif self.cell is not None and tag == "a":
            self.cell["url"] = props.get("href", "") or ""
        elif self.cell is not None and tag == "br":
            self.cell["parts"].append(" ")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["parts"].append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append({"text": " ".join(" ".join(self.cell["parts"]).split()),
                             "url": self.cell["url"]})
            self.cell = None
        elif tag == "tr" and self.depth == 1 and self.row is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.depth:
            if self.depth == 1 and self.table is not None:
                self.tables.append(self.table)
                self.table = None
            self.depth -= 1


def _table(html, expected):
    parser = Tables()
    parser.feed(html)
    for t in parser.tables:
        if t and [c["text"].lower() for c in t[0][:len(expected)]] == list(expected):
            return t[1:]
    raise ValueError("financial disclosure source table missing or changed schema")


def parse_index(html):
    """Only accept rows explicitly linked to a seven-character Bioguide ID."""
    rows = _table(html, ("senator", "year", "assets", "debts", "net worth"))
    found = {}
    for r in rows:
        if len(r) < 5:
            continue
        m = ID_RE.search(r[0]["url"])
        if not m or not YEAR_RE.fullmatch(r[1]["text"]):
            continue
        year, assets, debts, net = r[1]["text"], r[2]["text"], r[3]["text"], r[4]["text"]
        if not all(VALUE_RE.fullmatch(v) for v in (assets, debts, net)):
            continue
        sid = m.group(1)
        record = {"year": int(year), "assets": assets, "debts": debts, "net_worth": net,
                  "profile_url": BASE + "/senator/" + sid,
                  "source_url": OFFICIAL}
        if sid in found and found[sid]["year"] >= record["year"]:
            continue
        found[sid] = record
    if len(found) < MIN_COVERAGE:
        raise ValueError(f"source returned only {len(found)} matching senator reports")
    return found


def parse_profile(html, year):
    """The page presents the largest holdings, not necessarily every asset."""
    rows = _table(html, ("asset", "kind", "owner", "value", "income"))
    stocks, other = [], []
    for r in rows:
        if len(r) < 4:
            continue
        name, kind, owner, value = [x["text"] for x in r[:4]]
        if not (name and kind and value and "$" in value and len(name) < 240):
            continue
        entry = {"name": name, "kind": kind, "owner": owner[:60], "range": value[:70]}
        if "stock" in kind.lower() or kind.lower() in ("equity", "equities", "shares"):
            stocks.append(entry)
        elif any(w in kind.lower() for w in ("fund", "trust", "etf", "bond")):
            other.append(entry)
    # This is a source-selected largest-holdings table, NOT an exhaustive portfolio.
    if not rows:
        raise ValueError("no holdings rows in annual report")
    filing = ""
    try:
        reports = _table(html, ("filed", "report", "entries"))
        for row in reports:
            if len(row) > 1 and f"Calendar {year}" in row[1]["text"] and "Annual" in row[1]["text"]:
                filing = row[0]["text"][:40]
                break
    except ValueError:
        pass
    return {"stocks": stocks[:8], "other_holdings": other[:5],
            "stock_rows_in_summary": len(stocks), "holdings_source": "largest holdings shown",
            "filed": filing, "details_checked": True}


def read_snapshot(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if data.get("schema") == "civicalign.senate_financials/1" else {"schema": "civicalign.senate_financials/1", "entries": {}}
    except (FileNotFoundError, ValueError):
        return {"schema": "civicalign.senate_financials/1", "entries": {}}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "CivicAlign public-civic-research/1.0 (source-attributed, no commercial use)"})
    with urllib.request.urlopen(req, timeout=25) as response:
        body = response.read(MAX_HTML + 1)
    if len(body) > MAX_HTML:
        raise ValueError("source page exceeds size limit")
    return body.decode("utf-8", errors="replace")


def refresh(path=None, fetch=None, *, now=None, force=False, delay=0.2):
    """Update snapshot or retain the last valid one on any source failure."""
    path = Path(path) if path else DEFAULT.ideology_dir.parent / "financials" / "senate.json"
    fetch = fetch or get
    now = now or datetime.now(timezone.utc)
    prior = read_snapshot(path)
    stamp = prior.get("checked_utc")
    if stamp and not force:
        try:
            checked = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if now - checked < timedelta(days=FRESH_DAYS) and len(prior.get("entries", {})) >= MIN_COVERAGE:
                return "current"
        except ValueError:
            pass
    try:
        index = parse_index(fetch(BASE + "/holdings"))
    except (ValueError, OSError, urllib.error.URLError, TimeoutError) as e:
        print(f"Financial disclosures: index unchanged ({type(e).__name__}: {str(e)[:140]})")
        return "source_unreachable"
    entries = {}
    succeeded = 0
    for sid, item in sorted(index.items()):
        original = prior.get("entries", {}).get(sid, {})
        if original and original.get("year", 0) > item["year"]:
            entries[sid] = original
            continue
        try:
            detail = parse_profile(fetch(item["profile_url"]), item["year"])
            item.update(detail)
            succeeded += 1
        except (ValueError, OSError, urllib.error.URLError, TimeoutError):
            if original.get("year") == item["year"] and original.get("details_checked"):
                for key in ("stocks", "other_holdings", "stock_rows_in_summary",
                            "holdings_source", "filed", "details_checked"):
                    if key in original:
                        item[key] = original[key]
                item["details_checked"] = False
            # Do not claim that a failed detail fetch means zero holdings.
        entries[sid] = item
        if delay:
            time.sleep(delay)
    if succeeded < MIN_COVERAGE:
        print(f"Financial disclosures: only {succeeded} profile pages checked; keeping prior snapshot")
        return "low_coverage"
    snapshot = {"schema": "civicalign.senate_financials/1",
                "source": BASE, "official_search": OFFICIAL,
                "checked_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "entries": entries}
    # Atomic local replacement: never replace good stored data with a partial scrape.
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pending.replace(path)
    return f"updated {len(entries)} reports, {succeeded} detailed profiles"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    print("Senate financial disclosures:", refresh(force=args.force))


if __name__ == "__main__":
    main()
