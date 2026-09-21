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
class BillReferral:
    """One bill's passage through one committee."""
    bill: str                # e.g. "S 100"
    sponsor: str             # bioguide id
    committee: str           # four-letter code, e.g. "SSBK"
    reported: bool           # did the committee let it out
    discharged: bool         # or was it forced out over the committee's head


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
