"""A bill's full official record from GovInfo's BILLSTATUS bulk XML.

billflow.py reads the same archives for committee referrals. This reader keeps
what Pillar 1 needs: origin chamber, titles, every published text version with
its GovInfo URL and date, every action with its recorded-vote links, and the
laws list. Nothing is inferred; every field is the government's own.
"""
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..agents.base import sha256_bytes


@dataclass(frozen=True)
class TextVersion:
    name: str            # "Engrossed in Senate"
    code: str            # "es", from the GovInfo package id
    date: str            # YYYY-MM-DD or "" (enrolled versions carry none)
    url: str             # the plain-xml URL (the uslm one is kept in `urls`)
    urls: tuple[str, ...]


@dataclass(frozen=True)
class RecordedVote:
    chamber: str         # "Senate" | "House"
    number: int
    url: str


@dataclass(frozen=True)
class Action:
    date: str
    text: str
    source: str          # actionCode/sourceSystem name where present
    recorded_votes: tuple[RecordedVote, ...]


@dataclass(frozen=True)
class BillRecord:
    congress: int
    bill_type: str       # "S", "HR", "SJRES", "HJRES"
    number: int
    origin_chamber: str  # "Senate" | "House"
    title: str
    short_title: str
    update_date: str
    text_versions: tuple[TextVersion, ...]
    actions: tuple[Action, ...]
    laws: tuple[str, ...]
    sha256: str          # of the XML bytes this record was read from
    filename: str

    @property
    def key(self) -> str:
        return f"{self.bill_type}{self.number}"


_PKG = re.compile(r"/BILLS-(\d+)([a-z]+)(\d+)([a-z]+)[./]", re.I)


_PLAW = re.compile(r"/PLAW-\d+(publ|pvtl)\d+[./]", re.I)


def version_code(url: str) -> str:
    m = _PKG.search(url or "")
    if m:
        return m.group(4).lower()
    return "pl" if _PLAW.search(url or "") else ""


def parse_bill(xml_bytes: bytes, filename: str = "") -> BillRecord | None:
    try:
        root = ET.parse(io.BytesIO(xml_bytes)).getroot()
    except ET.ParseError:
        return None
    b = root.find("bill")
    if b is None:
        return None
    g = lambda tag: (b.findtext(tag) or "").strip()
    versions = []
    tv = b.find("textVersions")
    if tv is not None:
        for it in tv.findall("item"):
            urls = tuple((f.findtext("url") or "").strip() for f in it.findall("formats/item"))
            plain = next((u for u in urls if "/xml/" in u), urls[0] if urls else "")
            versions.append(TextVersion(name=(it.findtext("type") or "").strip(),
                                        code=version_code(plain or (urls[0] if urls else "")),
                                        date=(it.findtext("date") or "")[:10], url=plain, urls=urls))
    actions = []
    for a in b.findall("actions/item"):
        rvs = tuple(RecordedVote(chamber=(v.findtext("chamber") or "").strip(),
                                 number=int((v.findtext("rollNumber") or "0").strip() or 0),
                                 url=(v.findtext("url") or "").strip())
                    for v in a.findall("recordedVotes/recordedVote"))
        actions.append(Action(date=(a.findtext("actionDate") or "")[:10], text=(a.findtext("text") or "").strip(),
                              source=(a.findtext("sourceSystem/name") or "").strip(), recorded_votes=rvs))
    short = ""
    for t in b.findall("titles/item"):
        if "Short Title" in (t.findtext("titleType") or "") and (t.findtext("title") or "").strip():
            short = (t.findtext("title") or "").strip()
            break
    return BillRecord(
        congress=int(g("congress") or 0), bill_type=g("type").upper().replace(".", ""), number=int(g("number") or 0),
        origin_chamber=g("originChamber"), title=g("title"), short_title=short, update_date=g("updateDate"),
        text_versions=tuple(versions), actions=tuple(actions),
        laws=tuple(f"{l.findtext('type')} {l.findtext('number')}".strip() for l in b.findall("laws/item")),
        sha256=sha256_bytes(xml_bytes), filename=filename,
    )


def load_records(*zip_paths: Path) -> dict[str, BillRecord]:
    """Every bill record in the given archives, keyed like Voteview: S2, HR1, SJRES18."""
    out: dict[str, BillRecord] = {}
    for zp in zip_paths:
        if not zp.exists():
            continue
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                if not name.endswith(".xml"):
                    continue
                rec = parse_bill(z.read(name), filename=name)
                if rec is not None:
                    out[rec.key] = rec
    return out
