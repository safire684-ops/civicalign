"""Stage 2.5: the source context and packet for every bound vote.

    PYTHONPATH=src python -m civicalign.explain.context [--offline]

For each Stage 2 binding this module:
  1. extracts the structured references in the voted text (external-xref
     elements with parsable citations; never a prose regex for the Code);
  2. applies the fixed section-selection policy;
  3. selects the U.S. Code release point in force at the vote and extracts the
     selected sections, byte-exact, from OLRC's archive for that release point;
  4. identifies and hashes cited Public Laws (extracting a section when one is
     cited, otherwise recording the law only);
  5. records the CRS summary and its relationship to the voted text;
  6. for CRA resolutions, binds the underlying Federal Register document by
     citation, identifies GAO determinations, and sources the statutory
     consequence (5 U.S.C. 801) from the Code in force;
  7. states source completeness and the generation state;
  8. writes a tracked context record for every binding and a source packet for
     the READY states, whose content fields are byte-exact copies of tracked,
     hashed artefacts.
No model is called and nothing is summarised.
"""
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from ..agents.base import sha256_bytes
from ..config import DEFAULT, Config
from ..sources import federal_register as fr, publaw, uscode
from . import binding as B
from .fetch import Store

CONTEXT_SCHEMA = "civicalign.context/1.0"
PACKET_SCHEMA = "civicalign.packet/1.0"
SECTION_CAP = 12                 # more cited sections than this and the selection policy for large measures is needed
LARGE_TEXT_WORDS = 30000         # above this a packet needs a section-selection policy for the text itself (not built)
CRA_CONSEQUENCE = ("5", "801")   # the CRA consequence: 5 U.S.C. 801 in the Code in force at the vote

AMENDATORY = re.compile(r"\bis amended\b|\bare amended\b|\bis repealed\b|\bby striking\b|\bby inserting\b|\bis redesignated\b|\bare redesignated\b")
BLOCKS = {"text", "clause", "subclause", "subparagraph", "paragraph", "subsection", "section", "quoted-block", "resolution-body", "legis-body"}

# ---- references ----------------------------------------------------------------

def extract_references(xml_bytes: bytes) -> list[dict]:
    root = ET.parse(io.BytesIO(xml_bytes)).getroot()
    parent = {c: p for p in root.iter() for c in p}
    out = []
    for x in root.iter("external-xref"):
        cite = x.get("parsable-cite", ""); ld = x.get("legal-doc", "")
        block = parent.get(x)
        while block is not None and block.tag not in BLOCKS:
            block = parent.get(block)
        btext = " ".join("".join(block.itertext()).split()) if block is not None else ""
        rec = {"legal_doc": ld, "cite": cite, "text": "".join(x.itertext()).strip(),
               "amendatory": bool(AMENDATORY.search(btext)), "pl_section": None, "pl_division": None}
        if ld == "public-law":
            pl = publaw.parse_cite(cite)
            if pl:
                for m in publaw.SECTION_OF_PL.finditer(btext):
                    if (int(m.group(2)), int(m.group(3))) == pl:
                        rec["pl_section"] = m.group(1); break
                if rec["pl_section"] is None:
                    for m in publaw.DIVISION_OF_PL.finditer(btext):
                        if (int(m.group(2)), int(m.group(3))) == pl:
                            rec["pl_division"] = m.group(1); break
        out.append(rec)
    return out


def select_sections(refs: list[dict], is_cra: bool) -> dict:
    """The fixed policy. Sections cited inside amendatory instructions are
    required; if there are none, every cited section is required (a short
    measure's authorities); above SECTION_CAP the large-measure policy, which
    does not exist yet, is needed and the context stays pending."""
    ids = {}
    for r in refs:
        if r["legal_doc"] != "usc":
            continue
        u = uscode.usc_identifier(r["cite"])
        if u:
            ids.setdefault(u[2], {"title": u[0], "section": u[1], "amendatory": False})
            ids[u[2]]["amendatory"] |= r["amendatory"]
    amend = sorted(k for k, v in ids.items() if v["amendatory"])
    if is_cra:
        return {"policy": "cra: the resolution's own text and the CRA consequence section; cited authorities are not extracted",
                "section_cap": SECTION_CAP, "required": [], "cited": sorted(ids), "amended": amend, "status": "ok"}
    required = amend if amend else sorted(ids)
    if len(required) > SECTION_CAP:
        return {"policy": "amended sections if any, else all cited sections; capped", "section_cap": SECTION_CAP,
                "required": [], "cited": sorted(ids), "amended": amend, "status": "exceeds_cap",
                "reason": f"{len(required)} sections exceed the cap of {SECTION_CAP}; the large-measure selection policy is not built"}
    return {"policy": "amended sections if any, else all cited sections; capped", "section_cap": SECTION_CAP,
            "required": required, "cited": sorted(ids), "amended": amend, "status": "ok"}


# ---- official summary ------------------------------------------------------------

def bill_summaries(cfg: Config, bill_type: str, filename: str) -> list[dict]:
    zp = {"S": cfg.billflow_zip, "HR": cfg.billflow_house_zip, "SJRES": cfg.billstatus_sjres_zip, "HJRES": cfg.billstatus_hjres_zip}.get(bill_type)
    if not zp or not zp.exists():
        return []
    with zipfile.ZipFile(zp) as z:
        try:
            data = z.read(filename)
        except KeyError:
            return []
    root = ET.parse(io.BytesIO(data)).getroot().find("bill")
    out = []
    for s in root.findall("summaries/summary") if root is not None else []:
        text = (s.findtext("text") or "")
        out.append({"version_code": s.findtext("versionCode"), "action_desc": s.findtext("actionDesc"),
                    "action_date": (s.findtext("actionDate") or "")[:10], "text": text, "sha256": sha256_bytes(text.encode())})
    return out


def summary_relationship(summaries: list[dict], vote_date: str, text_code: str) -> dict:
    amended_text = text_code in ("es", "eas", "cps")
    same_day_senate = [s for s in summaries if s["action_desc"] == "Passed Senate" and s["action_date"] == vote_date]
    if same_day_senate:
        s = same_day_senate[0]; rel = "MATCHED"
    else:
        earlier = [s for s in summaries if s["action_date"] and s["action_date"] <= vote_date]
        if not earlier:
            return {"status": "none", "version_relationship": "UNKNOWN", "usable": False}
        s = max(earlier, key=lambda x: x["action_date"])
        rel = "PRE_AMENDMENT" if amended_text else "EARLIER_SAME_TEXT"
    return {"status": "available", "version_code": s["version_code"], "action_desc": s["action_desc"], "action_date": s["action_date"],
            "sha256": s["sha256"], "version_relationship": rel, "usable": rel in ("MATCHED", "EARLIER_SAME_TEXT"), "_text": s["text"]}


# ---- CRA ---------------------------------------------------------------------------

GAO = re.compile(r"letter of opinion from the Government Accountability Office dated ([A-Z][a-z]+ \d{1,2}, \d{4}).*?"
                 r"Congressional Record on ([A-Z][a-z]+ \d{1,2}, \d{4}), on pages? (S\d+(?:[–-]S\d+)?)", re.S)


def gao_determination(text: str) -> dict | None:
    m = GAO.search(text)
    if not m:
        return None
    f = lambda s: datetime.strptime(s, "%B %d, %Y").strftime("%Y-%m-%d")
    return {"type": "GAO_RULE_DETERMINATION", "opinion_date": f(m.group(1)), "congressional_record_date": f(m.group(2)),
            "congressional_record_pages": m.group(3).replace("–", "-"), "status": "identified_not_retrieved",
            "source_url": None, "sha256": None}


def bind_rule(store: Store, cra: dict, text: str, offline: bool) -> dict:
    cite = fr.citation_in(text)
    if cite is None:
        return {"status": "RULE_NOT_FOUND", "citation": None, "reason": "no Federal Register citation in the resolution text"}
    vol, page, day = cite
    windows = [fr.day_params(day)] if day else [fr.window_params(f"{fr.volume_year(vol)}-01-01", f"{fr.volume_year(vol)}-03-31")]
    hits = []
    for params in windows:
        pageno = 1
        while True:
            key = f"fr/q_{sha256_bytes(fr.query_url(params, pageno).encode())[:16]}.json"
            f = store.fetch(fr.query_url(params, pageno), key, min_bytes=20, offline=offline)
            if not f.ok:
                return {"status": "RULE_NOT_FOUND", "citation": f"{vol} FR {page}", "reason": "Federal Register API not reachable"}
            docs, pages = fr.parse_results(f.path.read_bytes())
            hits += fr.match_citation(docs, vol, page)
            if pageno >= pages or pageno >= 5:
                break
            pageno += 1
    hits = list({h.document_number: h for h in hits}.values())
    if not hits:
        return {"status": "RULE_NOT_FOUND", "citation": f"{vol} FR {page}", "reason": "no document starts at that page"}
    agree = [h for h in hits if fr.title_agrees(cra["rule_title"], h.title)]
    if len(hits) > 1 and len(agree) != 1:
        return {"status": "RULE_AMBIGUOUS", "citation": f"{vol} FR {page}", "candidates": [h.document_number for h in hits]}
    h = agree[0] if agree else hits[0]
    rec = {"status": "RULE_BOUND" if agree else "RULE_BOUND_TITLE_DIFFERS", "citation": h.citation, "document_number": h.document_number,
           "fr_title": h.title, "type": h.type, "publication_date": h.publication_date, "agencies": list(h.agencies),
           "source_url": h.html_url, "full_text_xml_url": h.full_text_xml_url, "sha256": None, "bytes": None}
    if h.full_text_xml_url:
        f = store.fetch(h.full_text_xml_url, f"fr/{h.document_number}.xml", min_bytes=500, offline=offline, immutable=True)
        if f.ok:
            rec["sha256"], rec["bytes"] = f.sha256, f.size
        else:
            rec["status"] = "RULE_BOUND_TEXT_PENDING"
    return rec


# ---- the Code in force -------------------------------------------------------------

class Code:
    def __init__(self, cfg: Config, store: Store, offline: bool):
        self.cfg, self.store, self.offline = cfg, store, offline
        self.points = self._points()
        self._titles: dict[str, bytes | None] = {}
        self.published: dict[str, set[str]] = {}
        self.classification = self._classification()

    def _points(self) -> list[uscode.ReleasePoint]:
        html = ""
        for url, rel in ((uscode.PRIOR_URL, "uscode/priorreleasepoints.htm"), (uscode.CURRENT_URL, "uscode/download.shtml")):
            f = self.store.fetch(url, rel, min_bytes=1000, offline=self.offline, allow_html=True)
            if f.ok:
                html += f.path.read_text(errors="ignore")
        return uscode.parse_release_points(html)

    def _classification(self) -> dict[str, set[tuple[str, str]]]:
        out: dict[str, set[tuple[str, str]]] = {}
        for session in ("1st", "2nd"):
            url = uscode.CLASSIFICATION_URL.format(congress=self.cfg.congress, session=session)
            f = self.store.fetch(url, f"uscode/tbl{self.cfg.congress}pl_{session}.htm", min_bytes=1000, offline=self.offline, allow_html=True)
            if f.ok:
                for k, v in uscode.parse_classification(f.path.read_text(errors="ignore")).items():
                    out.setdefault(k, set()).update(v)
        return out

    def listed(self, rp: uscode.ReleasePoint) -> set[str]:
        if rp.label not in self.published:
            f = self.store.fetch(uscode.RP_PAGE_URL.format(congress=rp.congress, law=rp.law), f"uscode/usc-rp@{rp.label}.htm",
                                 min_bytes=500, offline=self.offline, allow_html=True, immutable=True)
            self.published[rp.label] = uscode.archives_listed(f.path.read_text(errors="ignore"), rp) if f.ok else set()
        return self.published[rp.label]

    def in_force(self, vote_date: str, cite_title: str, section: str) -> dict:
        d = date.fromisoformat(vote_date)
        for p in [p for p in self.points if p.date <= d][::-1][:12]:   # look back at most twelve release points
            self.listed(p)
        return uscode.in_force_for_section(self.points, self.published, self.classification, vote_date, cite_title, section)

    def title(self, cite_title: str, rp: uscode.ReleasePoint) -> tuple[bytes | None, str, str | None]:
        """(title xml, archive sha256, problem). Archives are large; a partial
        download left by another process is treated as not yet available."""
        name = uscode.archive_name(cite_title, rp); rel = f"uscode/{name}"
        if rel in self._titles:
            return self._titles[rel]
        part = self.store.root / (rel + ".part")
        if part.exists():
            self._titles[rel] = (None, "", "archive download in progress"); return self._titles[rel]
        f = self.store.fetch(uscode.archive_url(cite_title, rp), rel, timeout=900, min_bytes=10_000, offline=self.offline, immutable=True)
        if not f.ok:
            self._titles[rel] = (None, "", "archive not retrievable"); return self._titles[rel]
        try:
            data = uscode.read_title(f.path)
        except (zipfile.BadZipFile, ValueError):
            self._titles[rel] = (None, f.sha256, "archive unreadable"); return self._titles[rel]
        pub = uscode.publication_name(data)
        if pub and pub != f"Online@{rp.label}":
            self._titles[rel] = (None, f.sha256, f"archive publication {pub!r} is not {rp.label}"); return self._titles[rel]
        self._titles[rel] = (data, f.sha256, None)
        return self._titles[rel]

    def section(self, cite_title: str, section: str, vote_date: str, relationship: str) -> dict:
        ident = f"/us/usc/t{cite_title}/s{section}"
        rec = {"type": "us_code", "identifier": ident, "title": cite_title, "section": section, "as_of": None,
               "source_url": None, "archive_sha256": None, "fragment_sha256": None, "bytes": None,
               "heading": None, "relationship": relationship, "status": "pending"}
        chk = self.in_force(vote_date, cite_title, section)
        rec["in_force_check"] = {k: v for k, v in chk.items() if k != "release_point"}
        if chk["status"] == "no_release_point":
            rec["status"] = "no_release_point"; return rec
        if chk["status"] == "no_published_archive":
            rec["status"] = "archive_unavailable"; rec["reason"] = f"no published archive for title {cite_title} at or before the vote (latest release point {chk['latest_release_point']})"; return rec
        rp = chk["release_point"]
        rec["as_of"] = {"release_point": rp.label, "date": rp.date.isoformat(),
                        "rule": "latest OLRC release point on or before the vote with a published archive; intervening laws checked against the classification table"}
        rec["source_url"] = uscode.archive_url(cite_title, rp)
        if chk["status"] == "ambiguous":
            rec["status"] = "in_force_ambiguous"; rec["reason"] = f"laws enacted after the last published archive may have changed this section: {chk['affected_by']}"; return rec
        data, ash, problem = self.title(cite_title, rp)
        rec["archive_sha256"] = ash or None
        if data is None:
            rec["status"] = "archive_unavailable"; rec["reason"] = problem; return rec
        frag = uscode.extract_section(data, ident)
        if frag is None:
            rec["status"] = "section_not_found"; return rec
        rec.update({"fragment_sha256": sha256_bytes(frag), "bytes": len(frag), "heading": uscode.section_heading(frag), "status": "fetched", "_content": frag.decode("utf8", "ignore")})
        return rec


# ---- per-vote context ----------------------------------------------------------------

def build_context(cfg: Config, b: dict, store: Store, code: Code, offline: bool) -> tuple[dict, dict | None]:
    v, tb, obj = b["vote"], b["text_binding"], b["object"]
    text_path = store.root / "text" / tb["govinfo_url"].rsplit("/", 1)[-1]
    kind_ok = b["classification"]["kind"] in B.SUPPORTED_KINDS
    ctx = {"schema": CONTEXT_SCHEMA,
           "vote": {"congress": v["congress"], "session": v["session"], "clerk_number": v["clerk_number"], "date": v["date"], "measure": obj["id"]},
           "binding": {"kind": b["classification"]["kind"], "verification": b["verification"]["status"], "text_status": tb["status"], "text_sha256": tb["sha256"]},
           "references": [], "selection": None, "release_point": None, "existing_law_context": [], "public_laws": [],
           "official_summary": {"status": "none", "version_relationship": "UNKNOWN", "usable": False},
           "cra": {"mode": "not_cra", "rule_status": None, "consequence_source": None, "underlying_rule": None, "gao_determination": None},
           "completeness": {"status": "PENDING", "missing": [], "notes": []}, "generation": {"status": "UNSUPPORTED"}}
    missing, notes = ctx["completeness"]["missing"], ctx["completeness"]["notes"]
    if not kind_ok:
        ctx["completeness"]["status"] = "PENDING"; return ctx, None
    if b["verification"]["status"] != "VERIFIED" or tb["status"] != B.TEXT_BOUND or not text_path.exists():
        missing.append("verified binding with bound text"); ctx["generation"]["status"] = "SOURCE_CONTEXT_PENDING"; return ctx, None
    xml_bytes = text_path.read_bytes()
    if sha256_bytes(xml_bytes) != tb["sha256"]:
        missing.append("voted text hash no longer matches the binding"); ctx["completeness"]["status"] = "AMBIGUOUS"
        ctx["generation"]["status"] = "SOURCE_CONTEXT_AMBIGUOUS"; return ctx, None
    plain = " ".join("".join(ET.parse(io.BytesIO(xml_bytes)).getroot().itertext()).split())
    words = len(plain.split())
    is_cra = bool(b["cra"]["is_cra"])
    refs = extract_references(xml_bytes); ctx["references"] = refs
    sel = select_sections(refs, is_cra); ctx["selection"] = sel
    rp = uscode.in_force(code.points, v["date"])
    ctx["release_point"] = {"label": rp.label, "date": rp.date.isoformat(), "note": "latest release point on or before the vote; per-section archives may come from an earlier published one"} if rp else None

    ambiguous = False
    # U.S. Code sections required by the policy
    for ident in sel["required"]:
        t, s = ident.split("/t")[1].split("/s")
        rel = "amended_by_bound_measure" if ident in sel["amended"] else "cited_as_authority"
        if rp is None:
            ctx["existing_law_context"].append({"type": "us_code", "identifier": ident, "status": "no_release_point", "relationship": rel})
            if code.points:
                missing.append(f"us_code:{ident} (no release point on or before the vote)"); ambiguous = True
            else:
                missing.append(f"us_code:{ident} (release point list unavailable)")
            continue
        rec = code.section(t, s, v["date"], rel); ctx["existing_law_context"].append(rec)
        if rec["status"] == "archive_unavailable":
            if rec.get("reason") == "archive download in progress":
                missing.append(f"us_code:{ident} (archive pending)")
            else:
                missing.append(f"us_code:{ident} (release point not retrievable)"); ambiguous = True
        elif rec["status"] != "fetched":
            missing.append(f"us_code:{ident} ({rec['status']})"); ambiguous = True
    if sel["status"] == "exceeds_cap":
        missing.append("section selection for a large measure"); notes.append(sel["reason"])
    if words > LARGE_TEXT_WORDS and not is_cra:
        missing.append("text section-selection policy for a large text"); notes.append(f"voted text is {words:,} words")

    # Public Laws cited
    seen = set()
    for r in refs:
        if r["legal_doc"] != "public-law" or r["cite"] in seen:
            continue
        seen.add(r["cite"]); pl = publaw.parse_cite(r["cite"])
        if not pl:
            continue
        sections = sorted({x["pl_section"] for x in refs if x["cite"] == r["cite"] and x["pl_section"]})
        divisions = sorted({x["pl_division"] for x in refs if x["cite"] == r["cite"] and x["pl_division"]})
        rec = {"type": "public_law", "cite": r["cite"], "congress": pl[0], "law": pl[1], "source_url": publaw.law_url(*pl),
               "sha256": None, "bytes": None, "sections": sections, "divisions": divisions, "fragments": [], "status": "pending",
               "relationship": "amended_by_bound_measure" if any(x["amendatory"] for x in refs if x["cite"] == r["cite"]) else "cited"}
        f = store.fetch(rec["source_url"], f"publaw/PLAW-{pl[0]}publ{pl[1]}.xml", timeout=600, min_bytes=1000, offline=offline, immutable=True)
        if f.ok and publaw.looks_like_uslm(f.path.read_bytes()[:600]):
            data = f.path.read_bytes(); rec["sha256"], rec["bytes"] = f.sha256, f.size; rec["status"] = "identified"
            for sec in sections:
                frag = publaw.extract_section(data, sec)
                if frag is None:
                    rec["fragments"].append({"section": sec, "status": "section_not_found"}); missing.append(f"public_law:{r['cite']}/s{sec}"); ambiguous = True
                else:
                    rec["fragments"].append({"section": sec, "fragment_sha256": sha256_bytes(frag), "bytes": len(frag), "status": "fetched", "_content": frag.decode("utf8", "ignore")})
            if not sections:
                notes.append(f"{r['cite']} cited as a whole law{' (' + ', '.join(divisions) + ')' if divisions else ''}: identified and hashed, no section extracted; the Maker may not describe its contents")
        else:
            rec["status"] = "unavailable"; rec["reason"] = "GovInfo does not serve this law as USLM (laws before the USLM era need the Statutes at Large)"
            missing.append(f"public_law:{r['cite']} (text pending)")
        ctx["public_laws"].append(rec)

    # CRS summary
    summaries = bill_summaries(cfg, obj["id"].rstrip("0123456789"), Path(obj["billstatus_source"] or "").name)
    ctx["official_summary"] = summary_relationship(summaries, v["date"], tb["version_code"])

    # CRA
    if is_cra:
        ctx["cra"]["mode"] = "resolution_only"
        cons = code.section(CRA_CONSEQUENCE[0], CRA_CONSEQUENCE[1], v["date"], "cra_statutory_consequence") if rp else None
        ctx["cra"]["consequence_source"] = cons
        if cons is None or cons["status"] != "fetched":
            missing.append(f"us_code:/us/usc/t5/s801@{rp.label if rp else '?'} (CRA consequence)")
            if cons is not None and cons["status"] not in ("archive_unavailable",):
                ambiguous = True
        gao = gao_determination(plain); ctx["cra"]["gao_determination"] = gao
        rule = bind_rule(store, b["cra"], plain, offline)
        ctx["cra"]["rule_status"] = "GAO_RULE_DETERMINATION" if (gao and rule["status"] == "RULE_NOT_FOUND") else rule["status"]
        ctx["cra"]["underlying_rule"] = rule if rule["status"].startswith("RULE_BOUND") else None
        if rule["status"] in ("RULE_BOUND", "RULE_BOUND_TITLE_DIFFERS") and rule.get("sha256"):
            ctx["cra"]["mode"] = "rule_bound"
        notes.append("CRA: the resolution's own effect may be explained; the underlying rule's substance may not unless the rule is bound and separately verified")

    # completeness and generation state
    if ambiguous:
        ctx["completeness"]["status"] = "AMBIGUOUS"; ctx["generation"]["status"] = "SOURCE_CONTEXT_AMBIGUOUS"
    elif missing:
        ctx["completeness"]["status"] = "PENDING"; ctx["generation"]["status"] = "SOURCE_CONTEXT_PENDING"
    elif is_cra:
        ctx["completeness"]["status"] = "LIMITED"; ctx["generation"]["status"] = "READY_WITH_LIMITS"
    else:
        ctx["completeness"]["status"] = "COMPLETE"; ctx["generation"]["status"] = "READY_FOR_GENERATION"

    packet = None
    if ctx["generation"]["status"] in ("READY_FOR_GENERATION", "READY_WITH_LIMITS"):
        packet = build_packet(b, ctx, xml_bytes, store)
    # strip private content from the tracked context record
    for rec in ctx["existing_law_context"]:
        rec.pop("_content", None)
    for pl in ctx["public_laws"]:
        for fr_ in pl["fragments"]:
            fr_.pop("_content", None)
    if ctx["cra"]["consequence_source"]:
        ctx["cra"]["consequence_source"].pop("_content", None)
    ctx["official_summary"].pop("_text", None)
    return ctx, packet


def build_packet(b: dict, ctx: dict, xml_bytes: bytes, store: Store) -> dict:
    """Everything the Maker may cite, byte-exact from tracked artefacts."""
    v, tb, obj = b["vote"], b["text_binding"], b["object"]
    law = []
    for rec in ctx["existing_law_context"]:
        if rec["status"] == "fetched":
            law.append({"type": "us_code", "identifier": rec["identifier"], "heading": rec["heading"], "as_of": rec["as_of"],
                        "sha256": rec["fragment_sha256"], "relationship": rec["relationship"], "content": rec["_content"]})
    for pl in ctx["public_laws"]:
        for fr_ in pl["fragments"]:
            if fr_["status"] == "fetched":
                law.append({"type": "public_law", "identifier": f"{pl['cite']}/s{fr_['section']}", "as_of": {"enacted_law": f"Public Law {pl['congress']}-{pl['law']}"},
                            "sha256": fr_["fragment_sha256"], "relationship": pl["relationship"], "content": fr_["_content"]})
    cited_laws = [{"type": "public_law", "identifier": pl["cite"], "sha256": pl["sha256"], "divisions": pl["divisions"], "content_included": False,
                   "note": "identified and hashed only; not to be described"} for pl in ctx["public_laws"] if not pl["sections"]]
    cra = ctx["cra"]
    cra_packet = {"mode": cra["mode"]}
    if cra["mode"] != "not_cra":
        cons = cra["consequence_source"]
        cra_packet["statutory_consequence_source"] = {"type": "us_code", "identifier": cons["identifier"], "as_of": cons["as_of"], "sha256": cons["fragment_sha256"], "content": cons["_content"]} if cons and cons["status"] == "fetched" else None
        cra_packet["resolution_identifies"] = {"agency": b["cra"]["agency"], "rule_title": b["cra"]["rule_title"], "citation": (cra["underlying_rule"] or {}).get("citation")}
        cra_packet["underlying_rule"] = None
        if cra["mode"] == "rule_bound":
            r = cra["underlying_rule"]; raw = store.root / f"fr/{r['document_number']}.xml"
            cra_packet["underlying_rule"] = {"document_number": r["document_number"], "citation": r["citation"], "fr_title": r["fr_title"], "type": r["type"],
                                             "publication_date": r["publication_date"], "agencies": r["agencies"], "sha256": r["sha256"],
                                             "content_included": False, "note": "bound and hashed; content is withheld until the CRA validation cohort passes"}
        cra_packet["limits"] = ["Senate passage is not enactment: the CRA consequence follows only if the joint resolution is enacted",
                                "the underlying rule's substance, who it affects, its costs or benefits, and the effect of removing it may not be described"
                                + ("" if cra["mode"] == "rule_bound" else " (no underlying rule is bound)")]
    summ = ctx["official_summary"]
    summary_packet = {"status": summ["status"], "version_relationship": summ["version_relationship"], "usable": summ["usable"]}
    if summ["status"] == "available":
        summary_packet.update({"version_code": summ["version_code"], "action_desc": summ["action_desc"], "action_date": summ["action_date"], "sha256": summ["sha256"]})
        if summ["usable"]:
            summary_packet["content"] = summ["_text"]
        else:
            summary_packet["warning"] = "describes an earlier version of the text; excluded from generation"
    return {"packet_schema": PACKET_SCHEMA,
            "vote": {**v, "senator_votes_source": "block F / S119_votes.csv (not included here)"},
            "legislative_object": {"type": obj["type"], "id": obj["id"], "title": obj["title"], "short_title": obj["short_title"], "origin_chamber": obj["origin_chamber"]},
            "classification": {"kind": b["classification"]["kind"]},
            "receipt_scaffold": b["receipt"],
            "voted_text": {"version_code": tb["version_code"], "version_name": tb["version_name"], "date": tb["version_date"], "url": tb["govinfo_url"],
                           "sha256": tb["sha256"], "format": "govinfo-bill-xml", "content": xml_bytes.decode("utf8", "ignore")},
            "existing_law_context": law, "cited_public_laws_not_included": cited_laws,
            "official_summary": summary_packet, "cra_context": cra_packet,
            "completeness": ctx["completeness"], "generation": ctx["generation"],
            "maker_rules": ["factual claims only from the content fields of this packet", "no browsing, no retrieval, no model memory for facts",
                            "derived metadata (headings, relationships, statuses) is not source text"]}


# ---- files and runner --------------------------------------------------------------

def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in ("history", "recorded_utc")}


def write_json(path: Path, doc: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if path.exists():
        old = json.loads(path.read_text())
        if _strip(old) == _strip(doc):
            return "unchanged"
        hist = old.get("history", []); prev = _strip(old); prev["superseded_utc"] = stamp; hist.append(prev)
        path.write_text(json.dumps(dict(doc, history=hist, recorded_utc=stamp), indent=1, ensure_ascii=False) + "\n"); return "changed"
    path.write_text(json.dumps(dict(doc, history=[], recorded_utc=stamp), indent=1, ensure_ascii=False) + "\n"); return "new"


def run(cfg: Config = DEFAULT, offline: bool = False, verbose: bool = True, only: set[str] | None = None) -> dict:
    store = Store(cfg.explain_raw_dir); code = Code(cfg, store, offline)
    bdir = cfg.bindings_dir; cdir = bdir / "context"; pdir = bdir / "packets"
    gen, comp, writes = Counter(), Counter(), Counter()
    rows = []
    for f in sorted(bdir.glob("vote_*.json")):
        b = json.loads(f.read_text())
        if only and b["object"]["id"] not in only:
            continue
        ctx, packet = build_context(cfg, b, store, code, offline)
        writes[write_json(cdir / f.name.replace(".json", ".context.json"), ctx)] += 1
        ppath = pdir / f.name.replace(".json", ".packet.json")
        if packet is not None:
            writes["packet_" + write_json(ppath, packet)] += 1
        elif ppath.exists():
            ppath.unlink(); writes["packet_removed"] += 1
        gen[ctx["generation"]["status"]] += 1; comp[ctx["completeness"]["status"]] += 1
        rows.append((b["object"]["id"], b["vote"]["date"], ctx["generation"]["status"], ctx["completeness"]["status"], ctx["cra"]["mode"], ctx["cra"]["rule_status"],
                     ctx["official_summary"]["version_relationship"], len([x for x in ctx["existing_law_context"] if x["status"] == "fetched"]), ctx["completeness"]["missing"][:2]))
    store.save()
    index = {"schema": CONTEXT_SCHEMA, "rule": {"section_cap": SECTION_CAP, "large_text_words": LARGE_TEXT_WORDS, "cra_consequence": "/us/usc/t5/s801",
                                                "release_point_rule": "latest OLRC release point dated on or before the vote; never a later one"},
             "generation": dict(gen), "completeness": dict(comp),
             "votes": [{"measure": r[0], "date": r[1], "generation": r[2], "completeness": r[3], "cra_mode": r[4], "rule_status": r[5], "summary": r[6], "law_sections": r[7]} for r in rows]}
    (cdir / "index.json").parent.mkdir(parents=True, exist_ok=True)
    write_json(cdir / "index.json", index)
    if verbose:
        for r in rows:
            print(f"  {r[0]:9s} {r[1]} {r[2]:26s} {r[3]:9s} {r[4]:15s} {str(r[5]):26s} {r[6]:17s} law={r[7]}  {r[8]}")
        print(json.dumps({"generation": dict(gen), "completeness": dict(comp), "writes": dict(writes)}, indent=1))
    return {"generation": dict(gen), "completeness": dict(comp), "writes": dict(writes)}


def main() -> int:
    offline = "--offline" in sys.argv
    only = {a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")}
    only = set(",".join(only).split(",")) if only else None
    run(DEFAULT, offline=offline, only=only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
