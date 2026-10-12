"""Full committee activity across all eight GovInfo measure types.

This deliberately does not change the Senate-bill-only sponsor / passage tables.
No count is returned unless every required archive matches the verified snapshot.
"""
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from ..config import DEFAULT, Config
from . import ingest as I

TYPES = ("s", "hr", "sres", "hres", "sjres", "hjres", "sconres", "hconres")
LABELS = {"s": "S.", "hr": "H.R.", "sres": "S.Res.", "hres": "H.Res.",
          "sjres": "S.J.Res.", "hjres": "H.J.Res.",
          "sconres": "S.Con.Res.", "hconres": "H.Con.Res."}
CONGRESS_TYPES = {"s": "senate-bill", "hr": "house-bill",
                  "sres": "senate-resolution", "hres": "house-resolution",
                  "sjres": "senate-joint-resolution", "hjres": "house-joint-resolution",
                  "sconres": "senate-concurrent-resolution",
                  "hconres": "house-concurrent-resolution"}
ACTIONS = ("Referred To", "Reported By", "Reported Original Measure")


def _text(node, key):
    return (node.findtext(key) or "").strip()


def read_measures(cfg: Config = DEFAULT):
    """Return measures and versions; never silently use partial/unverified inputs."""
    snap = I.snapshot(cfg)
    measures, versions = {}, {}
    for typ in TYPES:
        filename = f"BILLSTATUS-{cfg.congress}-{typ}.zip"
        entry = I.source_entry(cfg, snap, filename)
        versions[typ] = {"file": filename, "sha256": entry["sha256"],
                         "content_key": entry["content_key"],
                         "retrieved_at": entry["content_changed_utc"]}
        with zipfile.ZipFile(cfg.raw_dir / filename) as archive:
            for member in sorted(n for n in archive.namelist() if n.endswith(".xml")):
                root = ET.fromstring(archive.read(member))
                bill = root.find("bill")
                if bill is None:
                    raise ValueError(f"{filename}/{member}: missing bill element")
                congress, kind, number = _text(bill, "congress"), _text(bill, "type").lower(), _text(bill, "number")
                if congress != str(cfg.congress) or kind != typ or not number.isdecimal():
                    raise ValueError(f"{filename}/{member}: unexpected bill identity {congress} {kind} {number}")
                ident = kind.upper() + str(int(number))
                if ident in measures:
                    raise ValueError(f"duplicate measure {ident}")
                acts = {}
                for item in bill.findall("committees/item"):
                    code = _text(item, "systemCode").lower()
                    if not re.fullmatch(r"ss[a-z]{2}00", code) or _text(item, "chamber") != "Senate":
                        continue
                    events = [( _text(a, "name"), _text(a, "date")[:10])
                              for a in item.findall("activities/item")]
                    referred = sorted(d for name, d in events if name == "Referred To")
                    reported = sorted(d for name, d in events
                                      if name in ("Reported By", "Reported Original Measure"))
                    if referred or reported:
                        slot = acts.setdefault(code[:4].upper(), {"referred": [], "reported": []})
                        slot["referred"].extend(referred)
                        slot["reported"].extend(reported)
                measures[ident] = {
                    "id": ident, "type": typ, "number": int(number),
                    "label": LABELS[typ] + " " + str(int(number)),
                    "title": _text(bill, "title"),
                    "url": f"https://www.congress.gov/bill/{cfg.congress}th-congress/{CONGRESS_TYPES[typ]}/{int(number)}",
                    "committees": acts,
                }
    return measures, versions


def totals(cfg: Config = DEFAULT, codes=()):
    try:
        measures, versions = read_measures(cfg)
    except I.SnapshotMismatch as exc:
        # Existing snapshots and test fixtures may predate full coverage.
        # This is NOT zero committee activity: explicitly withhold the totals.
        return {"available": False, "reason": str(exc), "types": list(TYPES),
                "versions": {}, "committees": {}, "measures": {}}
    committees = {}
    for code in sorted(codes):
        referred = sorted((m["id"] for m in measures.values()
                           if m["committees"].get(code, {}).get("referred")))
        reported = sorted((m["id"] for m in measures.values()
                           if m["committees"].get(code, {}).get("reported")))
        by_type = {}
        for typ in TYPES:
            by_type[typ] = {
                "referred": [b for b in referred if measures[b]["type"] == typ],
                "reported": [b for b in reported if measures[b]["type"] == typ],
            }
        committees[code] = {
            "referred": referred, "reported": reported,
            "reported_without_referral": sorted(set(reported) - set(referred)),
            "by_type": by_type,
        }
    return {"available": True, "reason": None, "types": list(TYPES), "versions": versions, "committees": committees,
            "measures": {b: m for b, m in measures.items() if any(
                b in c["referred"] or b in c["reported"] for c in committees.values())}}
