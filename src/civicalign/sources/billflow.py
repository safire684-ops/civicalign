"""Every Senate bill's committee history, from the government's own bulk release.

WHY THIS EXISTS
---------------
Counting who sits on a committee measures its membership. This measures what the
committee actually DID: which bills it let out and which it buried. That is the
power a committee holds, and it is observable.

SOURCE, AND WHY NO API KEY IS NEEDED
------------------------------------
GovInfo bulk data, BILLSTATUS-119-s.zip -- about 13 MB holding one XML file per
Senate bill (5,428 for the 119th). Served as a plain file over HTTPS.

api.congress.gov returns 403 without a key and is rate limited; this bulk release
carries the same fields, needs no credential, and is a single request instead of
thousands. Nothing in this project should require a secret to reproduce.

Each bill gives us: the sponsor's bioguide id (so the sponsor's own ideological
score anchors the bill), every committee it was referred to, and each committee's
activities -- "Referred To", "Reported By", "Discharged From" and so on.
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


@dataclass(frozen=True)
class BillReferral:
    """One bill's passage through one committee."""
    bill: str                # e.g. "S 100"
    sponsor: str             # bioguide id
    committee: str           # four-letter code, e.g. "SSBK"
    reported: bool           # did the committee let it out
    discharged: bool         # or was it forced out over the committee's head


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


def load_referrals(zip_path: Path) -> list[BillReferral]:
    """Parse the bulk release into one row per bill-committee pair.

    A bill referred to two committees yields two rows: each committee had its own
    chance to bury it.
    """
    out: list[BillReferral] = []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.endswith(".xml"):
                continue
            with z.open(name) as fh:
                try:
                    bill = ET.parse(io.BytesIO(fh.read())).getroot().find("bill")
                except ET.ParseError:
                    continue
            if bill is None:
                continue

            sponsor = bill.find("sponsors/item")
            if sponsor is None:
                continue
            bioguide = sponsor.findtext("bioguideId")
            if not bioguide:
                continue

            label = f"{bill.findtext('type') or ''} {bill.findtext('number') or ''}".strip()

            for c in bill.findall("committees/item"):
                code = (c.findtext("systemCode") or "")[:4].upper()
                if not code:
                    continue
                acts = [a.findtext("name") or "" for a in c.findall("activities/item")]
                out.append(BillReferral(
                    bill=label,
                    sponsor=bioguide,
                    committee=code,
                    # "Reported By" and "Reported Original Measure" both mean the
                    # committee advanced it
                    reported=any("Reported" in a for a in acts),
                    # discharge is the floor overriding the committee, not the
                    # committee choosing to advance it -- counted separately
                    discharged=any("Discharged" in a for a in acts),
                ))
    return out
