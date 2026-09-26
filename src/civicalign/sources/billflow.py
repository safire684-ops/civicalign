"""Every bill's titles and Senate committee history, from the government's own bulk release.

Used by Pillar 1 (Engine A): the per-senator vote records and the recent floor
votes name each bill by its short or official title (receipts.py).

SOURCE, AND WHY NO API KEY IS NEEDED
------------------------------------
GovInfo bulk data, BILLSTATUS-119-s.zip and BILLSTATUS-119-hr.zip: one XML file
per bill, served as plain files over HTTPS. api.congress.gov returns 403 without
a key and is rate limited; this bulk release carries the same fields, needs no
credential, and is a single request instead of thousands. Nothing in this
project should require a secret to reproduce.

(The committee "bill flow" analysis that once read these archives -- which
bills each committee sent on -- is retired and removed.)
"""
import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Bill:
    key: str             # normalised number, e.g. "HR1"
    title: str           # official title
    short: str           # a short title where Congress gave one, else ""
    reported_by: frozenset[str]   # Senate committees that reported it out


def load_bills(*zip_paths: Path) -> dict[str, Bill]:
    """Every bill in the given bulk archives: title, short title, and the Senate
    committees that reported it. Senate and House archives both matter here,
    because House bills also pass through Senate committees."""
    out: dict[str, Bill] = {}
    for zip_path in zip_paths:
        if not zip_path.exists():
            continue
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                if not name.endswith(".xml"):
                    continue
                try:
                    bill = ET.parse(io.BytesIO(z.read(name))).getroot().find("bill")
                except ET.ParseError:
                    continue
                if bill is None:
                    continue
                key = f"{(bill.findtext('type') or '').upper()}{bill.findtext('number') or ''}"
                key = "".join(ch for ch in key if ch.isalnum())
                short = ""
                # A bill carries short titles for itself AND for sections inside it
                # ("...for portions of this bill"). Only the whole-bill one is the
                # name people know. Prefer the latest stage it was given.
                stage = {"enacted": 4, "passed senate": 3, "passed house": 2,
                         "reported": 1, "introduced": 0}
                best = -1
                for t in bill.findall("titles/item"):
                    kind = (t.findtext("titleType") or "").lower()
                    if "short" not in kind or "portion" in kind or not t.findtext("title"):
                        continue
                    rank = max((v for k, v in stage.items() if k in kind), default=0)
                    if rank > best:
                        best, short = rank, t.findtext("title").strip()
                reported = frozenset(
                    (c.findtext("systemCode") or "")[:4].upper()
                    for c in bill.findall("committees/item")
                    if (c.findtext("systemCode") or "").upper().startswith("S")
                    and any("Reported" in (a.findtext("name") or "")
                            for a in c.findall("activities/item"))
                )
                out[key] = Bill(key=key, title=(bill.findtext("title") or "").strip(),
                                short=short, reported_by=reported)
    return out
