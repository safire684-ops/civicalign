"""Senate roll calls as printed in the Congressional Record, from GovInfo.

The Record is the official account of Senate proceedings and prints every roll call by
name. GovInfo serves it to automated requests, unlike senate.gov, which has refused them
since October 2026. Each day's metadata names the page holding each roll call and each
"CHANGE OF VOTE" notice, so nothing here searches or guesses at pages.

This module reads and parses only. record_votes.py decides what the results mean.
"""
import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

USER_AGENT = "CivicAlign data pipeline (https://github.com/safire684-ops/civicalign)"
MODS = "https://www.govinfo.gov/metadata/pkg/CREC-{date}/mods.xml"
PAGE = "https://www.govinfo.gov/content/pkg/CREC-{date}/html/{granule}.htm"
VOTE_ID = re.compile(r"SENATE Rollcall Vote No\.\s*(\d+)")
GRANULE = re.compile(r"/(CREC-\d{4}-\d{2}-\d{2}-pt\d+-Pg[A-Za-z0-9-]+)$")
ROLL = re.compile(r"\s*\[Rollcall Vote No\.\s*(\d+)(?:\s+(Leg|Ex)\w*)?\.?\s*\]\s*", re.I)
SECTION = re.compile(r"^\s*(YEAS|NAYS|NOT VOTING|ANSWERED ``PRESENT''|PRESENT)\s*-{2,}\s*(\d+)\s*$")
ANNOUNCED = re.compile(r"yeas\s+(\d+),\s*nays\s+(\d+)", re.I)
NAME = re.compile(r"[A-Z][A-Za-z'’.\-]+(?: [A-Z][A-Za-z'’.\-]+)?(?: \([A-Z]{2}\))?")
POSITIONS = {"YEAS": "Yea", "NAYS": "Nay", "NOT VOTING": "Not Voting", "ANSWERED ``PRESENT''": "Present", "PRESENT": "Present"}
TAG = re.compile(r"</?(?:a|pre|html|head|title|body)\b[^>\n]*>")
SPEAKER = re.compile(r"\b(?:Mr|Ms|Mrs)\. ([A-Z][A-Z' -]+?)\. (?:Mr|Madam)\. President")
CHANGE = re.compile(r"(?:rollcall|roll call)\s+(?:vote\s+)?(?:No\.\s*)?(\d+)\b.{0,120}?intention\s+to\s+vote\s+[`']*(\w+)", re.I)
GRANTED = re.compile(r"Without objection, it is so ordered", re.I)
VOTE_WORDS = {"aye": "Yea", "yea": "Yea", "yes": "Yea", "nay": "Nay", "no": "Nay"}


class RecordError(RuntimeError):
    pass


def issue_url(date: str) -> str:
    return MODS.format(date=date)


def page_url(granule: str) -> str:
    return PAGE.format(date=re.match(r"CREC-(\d{4}-\d{2}-\d{2})", granule).group(1), granule=granule)


def fetch(url: str, cache: Path | None = None, pause: float = 0.2) -> bytes | None:
    """The bytes at url, or None when GovInfo has no such file. Other failures raise."""
    if cache is not None and cache.exists():
        return cache.read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as r:
                body = r.read()
                if urllib.parse.urlsplit(r.geturl()).path.startswith("/error"):
                    return None                    # GovInfo sends a missing file to an error page with status 200
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 403 or attempt == 2:      # a refusal is an answer; asking again won't change it
                raise RecordError(f"{url}: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                raise RecordError(f"{url}: {e}") from e
        time.sleep(2 ** attempt)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(body)
    time.sleep(pause)
    return body


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def issue_index(mods: bytes) -> dict:
    """{"votes": {roll number: granule}, "changes": [granule], "senate": [granule]} from a day's metadata."""
    votes, changes, senate = {}, [], []
    for node in ET.fromstring(mods).iter():
        ids = [c for c in node if _local(c.tag) == "identifier"]
        granule = next((m.group(1) for c in ids if c.get("type") == "uri" and (m := GRANULE.search((c.text or "").strip()))), None)
        if granule is None:
            continue
        for c in ids:
            if c.get("type") == "congressional vote number" and (m := VOTE_ID.search(c.text or "")):
                votes[int(m.group(1))] = granule
        titles = [(t.text or "").strip().upper() for t in node.iter() if _local(t.tag) == "title"]
        if "CHANGE OF VOTE" in titles and granule not in changes:
            changes.append(granule)
        if any(_local(x.tag) == "granuleClass" and (x.text or "").strip() == "SENATE" for x in node.iter()) and granule not in senate:
            senate.append(granule)
    return {"votes": votes, "changes": changes, "senate": senate}


def _lines(page: bytes) -> list[str]:
    return html.unescape(TAG.sub("", page.decode("utf-8", "replace"))).splitlines()


def parse_rolls(page: bytes) -> dict[int, dict]:
    """Each roll call printed on a page. A list that doesn't reach its printed total is
    reported as incomplete rather than guessed at."""
    lines, out = _lines(page), {}
    # A header stands alone on its line; a printed correction can quote one inside a paragraph.
    starts = [(i, m) for i, l in enumerate(lines) if (m := ROLL.fullmatch(l))]
    for k, (start, m) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        before = " ".join(lines[max(0, start - 8):start])
        said = ANNOUNCED.findall(before)
        roll = {"kind": (m.group(2) or "").title() or None, "announced": {"yea": int(said[-1][0]), "nay": int(said[-1][1])} if said else None, "lists": {}, "complete": True}
        i = start + 1
        while i < end:
            head = SECTION.match(lines[i])
            i += 1
            if not head:
                continue
            if POSITIONS[head.group(1)] in roll["lists"]:
                break
            want, names = int(head.group(2)), []
            while i < end and len(names) < want:
                line = lines[i].strip()
                if SECTION.match(lines[i]):
                    break
                i += 1
                if not line or line.startswith("[[Page") or line.startswith("{time}"):
                    continue
                cells = re.split(r"\s{2,}", line)
                if all(NAME.fullmatch(c) for c in cells):    # a printed note can interrupt a list
                    names += cells
            roll["lists"][POSITIONS[head.group(1)]] = names
            roll["complete"] = roll["complete"] and len(names) == want
        roll["complete"] = roll["complete"] and bool(roll["lists"])
        for position in ("Yea", "Nay"):
            roll["lists"].setdefault(position, [])
        out.setdefault(int(m.group(1)), roll)
    return out


def parse_changes(page: bytes) -> dict:
    """A change-of-vote notice: {"found": [{"number", "speaker", "to"}], "granted": bool}.
    A notice this can't read has an empty "found", which the caller reports."""
    text = " ".join(l.strip() for l in _lines(page))
    found = []
    for m in CHANGE.finditer(text):
        to = VOTE_WORDS.get(m.group(2).lower())
        speakers = SPEAKER.findall(text[:m.start()])
        if to and speakers:
            found.append({"number": int(m.group(1)), "speaker": speakers[-1], "to": to})
    return {"found": found, "granted": bool(GRANTED.search(text))}
