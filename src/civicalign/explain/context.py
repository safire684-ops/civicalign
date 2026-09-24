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
from . import binding as B, relevance as R
from .fetch import Store

CONTEXT_SCHEMA = "civicalign.context/1.1"
PACKET_SCHEMA = "civicalign.packet/1.1"
SECTION_CAP = 12                 # more cited sections than this and the selection policy for large measures is needed
LARGE_TEXT_WORDS = 30000         # above this a packet needs a section-selection policy for the text itself (not built)
CRA_CONSEQUENCE = ("5", "801")   # the CRA consequence: 5 U.S.C. 801 in the Code in force at the vote

FULL_SECTION_MAX_CHARS = 50000  # a whole cited section larger than this is never injected; a pinpoint or a policy decision is needed
PACKET_REVIEW_CHARS = 150000     # a packet whose source text exceeds this is flagged for human review (never truncated)

# ---- references and the selection policy ------------------------------------------

def extract_references(xml_bytes: bytes) -> list[dict]:
    """Every tagged citation in the voted XML with its location, scope, pinpoint
    and relationship (see relevance.py)."""
    return R.analyse(xml_bytes)["references"]


def citation_gaps(xml_bytes: bytes) -> list[dict]:
    return R.analyse(xml_bytes)["gaps"]


def _subsumed(ident: str, others: set[str]) -> bool:
    return any(ident != o and ident.startswith(o + "/") for o in others)


def select_sections(refs: list[dict], is_cra: bool, gaps: list[dict] | None = None) -> dict:
    """The fixed policy. U.S. Code provisions whose relationship needs content are
    required, at the node the citation names (a whole section only when the
    citation names only the section); a node inside another required provision
    is covered by it. Everything else is tracked, not included. CRA resolutions
    keep their own policy (the resolution's text and 5 U.S.C. 801 only). A
    citation the XML leaves unresolved in a location that needs content, or more
    required provisions than SECTION_CAP, leaves the context pending."""
    need: dict[str, dict] = {}; tracked: dict[str, dict] = {}
    for r in refs:
        if r["legal_doc"] != "usc":
            continue
        u = uscode.usc_identifier(r["cite"])
        if not u:
            continue
        ident = R.node_identifier(u[0], u[1], r["pinpoint"]) if r["scope"] == "node" else u[2]
        target = need if (r["relationship"] in R.REQUIRED and not is_cra) else tracked
        e = target.setdefault(ident, {"title": u[0], "section": u[1], "section_identifier": u[2], "scope": "node" if r["scope"] == "node" else "section",
                                      "relationships": [], "bases": []})
        if r["relationship"] not in e["relationships"]:
            e["relationships"].append(r["relationship"]); e["bases"].append(r["basis"])
        cited_as = {"text": r["text"], "source": r.get("source", "structured_xref"), "rule": r.get("rule")}
        e.setdefault("cited_as", [])
        if cited_as not in e["cited_as"]:
            e["cited_as"].append(cited_as)
    required = sorted(k for k in need if not _subsumed(k, set(need)))
    tracked_only = sorted(k for k in tracked if k not in need and not _subsumed(k, set(need)))
    relationships = {k: need[k]["relationships"] for k in required} | {k: tracked[k]["relationships"] for k in tracked_only}
    bases = {k: need[k]["bases"] for k in required} | {k: tracked[k]["bases"] for k in tracked_only}
    # a required provision also carries the citations of the nodes it covers
    cited_as = {k: need[k]["cited_as"] + [c for n in need if _subsumed(n, {k}) for c in need[n]["cited_as"] if c not in need[k]["cited_as"]]
                for k in required} | {k: tracked[k]["cited_as"] for k in tracked_only}
    unresolved = [g for g in (gaps or []) if g["relationship"] in R.REQUIRED and not g.get("resolved") and not is_cra]
    base = {"policy": ("cra: the resolution's own text and the CRA consequence section; cited authorities are tracked, not extracted" if is_cra else
                       "provisions whose relationship needs content, at the cited node; others tracked only; capped"),
            "section_cap": SECTION_CAP, "full_section_max_chars": FULL_SECTION_MAX_CHARS,
            "required": required, "tracked_only": tracked_only, "relationships": relationships, "bases": bases, "cited_as": cited_as,
            "cited": sorted({e["section_identifier"] for e in list(need.values()) + list(tracked.values())}),
            "amended": sorted(k for k in required if set(need[k]["relationships"]) & {R.AMENDED_TARGET, R.REPLACED_TEXT}),
            "unresolved_citations": unresolved, "resolved_by_fallback": [g for g in (gaps or []) if g.get("resolved")], "status": "ok"}
    if unresolved:
        base["status"] = "unresolved_citations"
        base["reason"] = f"{len(unresolved)} citation(s) in provisions that need content are not structured in the voted XML: {[g['text'] for g in unresolved]}"
    if len(required) > SECTION_CAP:
        base.update({"required": [], "status": "exceeds_cap",
                     "reason": f"{len(required)} provisions exceed the cap of {SECTION_CAP}; the large-measure selection policy is not built"})
    return base


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
        rec.update({"fragment_sha256": sha256_bytes(frag), "bytes": len(frag), "heading": uscode.section_heading(frag), "status": "fetched",
                    "_bytes": frag, "_content": frag.decode("utf8", "ignore")})
        return rec

    def provision(self, ident: str, title: str, section: str, vote_date: str, relationships: list[str], bases: list[str], include: bool) -> dict:
        """A cited provision at the node the citation names. The section is
        resolved in force at the vote as before; a node is then cut from it
        byte-exact, with the lead-in (number, heading, chapeau) of every provision
        above it. Content is kept only when the relationship needs it and it is
        not an oversized whole section."""
        section_id = f"/us/usc/t{title}/s{section}"
        rels = sorted(relationships, key=R.PRECEDENCE.index)
        rec = self.section(title, section, vote_date, rels[0])
        rec.update({"identifier": ident, "section_identifier": section_id, "scope": "section" if ident == section_id else "node",
                    "relationships": rels, "bases": bases, "inclusion": R.CONTENT_INCLUDED if include else R.REFERENCE_TRACKED, "hierarchy": []})
        if rec["status"] != "fetched":
            return rec
        sec = rec.pop("_bytes")
        rec["section_fragment_sha256"], rec["section_bytes"] = rec["fragment_sha256"], rec["bytes"]
        if rec["scope"] == "node":
            node = uscode.extract_node(sec, ident)
            if node is None:
                rec.pop("_content", None)
                rec.update({"status": "node_not_found", "fragment_sha256": None, "bytes": None,
                            "reason": f"{ident} is not an identifier in {section_id} at {rec['as_of']['release_point']}"})
                return rec
            frag = node[0]
            rec.update({"fragment_sha256": sha256_bytes(frag), "bytes": len(frag), "heading": uscode.section_heading(frag), "_content": frag.decode("utf8", "ignore")})
            parts = ident[len(section_id):].strip("/").split("/")
            for i in range(len(parts)):
                anc = section_id + "".join("/" + p for p in parts[:i])
                el = sec if anc == section_id else (uscode.extract_node(sec, anc) or (None,))[0]
                if el is None:
                    rec["status"] = "node_not_found"; rec["reason"] = f"ancestor {anc} not found"; rec.pop("_content", None); return rec
                li = uscode.lead_in(el)
                rec["hierarchy"].append({"identifier": anc, "sha256": sha256_bytes(li), "bytes": len(li), "_content": li.decode("utf8", "ignore")})
        elif include and len(rec["_content"]) > FULL_SECTION_MAX_CHARS:
            rec.pop("_content", None)
            rec.update({"status": "fragment_selection_required", "inclusion": R.REFERENCE_TRACKED,
                        "reason": f"the citation names only the whole section ({rec['section_bytes']:,} bytes, over {FULL_SECTION_MAX_CHARS:,} characters); "
                                  "a deterministic fragment cannot be chosen, so it is not injected"})
            return rec
        if not include:
            rec.pop("_content", None)
            for h in rec["hierarchy"]:
                h.pop("_content", None)
        return rec


# ---- per-vote context ----------------------------------------------------------------

def build_context(cfg: Config, b: dict, store: Store, code: Code, offline: bool) -> tuple[dict, dict | None]:
    v, tb, obj = b["vote"], b["text_binding"], b["object"]
    text_path = store.root / "text" / tb["govinfo_url"].rsplit("/", 1)[-1]
    kind_ok = b["classification"]["kind"] in B.SUPPORTED_KINDS
    ctx = {"schema": CONTEXT_SCHEMA,
           "vote": {"congress": v["congress"], "session": v["session"], "clerk_number": v["clerk_number"], "date": v["date"], "measure": obj["id"]},
           "binding": {"kind": b["classification"]["kind"], "verification": b["verification"]["status"], "text_status": tb["status"], "text_sha256": tb["sha256"]},
           "references": [], "citation_gaps": [], "selection": None, "release_point": None, "existing_law_context": [], "public_laws": [],
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
    analysed = R.analyse(xml_bytes)
    refs = analysed["references"]; ctx["references"] = refs
    sel = select_sections(refs, is_cra, analysed["gaps"]); ctx["selection"] = sel
    ctx["citation_gaps"] = analysed["gaps"]
    rp = uscode.in_force(code.points, v["date"])
    ctx["release_point"] = {"label": rp.label, "date": rp.date.isoformat(), "note": "latest release point on or before the vote; per-section archives may come from an earlier published one"} if rp else None

    ambiguous = False
    # U.S. Code provisions: required ones with content, the rest tracked (hash, no content)
    wanted = [(i, True) for i in sel["required"]] + [(i, False) for i in sel["tracked_only"]]
    for ident, include in wanted:
        t, rest = ident.split("/t", 1)[1].split("/s", 1)
        sec = rest.split("/", 1)[0]
        rels = sel["relationships"][ident]
        if rp is None:
            ctx["existing_law_context"].append({"type": "us_code", "identifier": ident, "status": "no_release_point", "relationships": rels,
                                                "inclusion": R.CONTENT_INCLUDED if include else R.REFERENCE_TRACKED})
            if include:
                missing.append(f"us_code:{ident} (no release point on or before the vote)" if code.points else f"us_code:{ident} (release point list unavailable)")
                ambiguous = ambiguous or bool(code.points)
            continue
        rec = code.provision(ident, t, sec, v["date"], rels, sel["bases"][ident], include)
        rec["cited_as"] = sel["cited_as"][ident]
        ctx["existing_law_context"].append(rec)
        if not include:
            continue
        if rec["status"] == "archive_unavailable":
            if rec.get("reason") == "archive download in progress":
                missing.append(f"us_code:{ident} (archive pending)")
            else:
                missing.append(f"us_code:{ident} (release point not retrievable)"); ambiguous = True
        elif rec["status"] in ("node_not_found", "fragment_selection_required"):
            missing.append(f"us_code:{ident} ({rec['status']})"); notes.append(rec["reason"])
        elif rec["status"] != "fetched":
            missing.append(f"us_code:{ident} ({rec['status']})"); ambiguous = True
    if sel["status"] == "unresolved_citations":
        missing.append("unresolved statutory citations in provisions that need content"); notes.append(sel["reason"])
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
        rels_of = lambda sec_: sorted({x["relationship"] for x in refs if x["cite"] == r["cite"] and x["pl_section"] == sec_}, key=R.PRECEDENCE.index)
        rec = {"type": "public_law", "cite": r["cite"], "congress": pl[0], "law": pl[1], "source_url": publaw.law_url(*pl),
               "sha256": None, "bytes": None, "sections": sections, "divisions": divisions, "fragments": [], "status": "pending",
               "relationships": sorted({x["relationship"] for x in refs if x["cite"] == r["cite"]}, key=R.PRECEDENCE.index)}
        f = store.fetch(rec["source_url"], f"publaw/PLAW-{pl[0]}publ{pl[1]}.xml", timeout=600, min_bytes=1000, offline=offline, immutable=True)
        if f.ok and publaw.looks_like_uslm(f.path.read_bytes()[:600]):
            data = f.path.read_bytes(); rec["sha256"], rec["bytes"] = f.sha256, f.size; rec["status"] = "identified"
            for sec in sections:
                rels = rels_of(sec); include = bool(set(rels) & R.REQUIRED) and not is_cra
                frag = publaw.extract_section(data, sec)
                entry = {"section": sec, "relationships": rels, "inclusion": R.CONTENT_INCLUDED if include else R.REFERENCE_TRACKED}
                if frag is None:
                    entry["status"] = "section_not_found"; rec["fragments"].append(entry)
                    if include:
                        missing.append(f"public_law:{r['cite']}/s{sec}"); ambiguous = True
                    continue
                entry.update({"fragment_sha256": sha256_bytes(frag), "bytes": len(frag), "status": "fetched"})
                content = frag.decode("utf8", "ignore")
                if include and len(content) > FULL_SECTION_MAX_CHARS:
                    entry.update({"status": "fragment_selection_required", "inclusion": R.REFERENCE_TRACKED,
                                  "reason": f"whole Public Law section of {len(frag):,} bytes, over {FULL_SECTION_MAX_CHARS:,} characters"})
                    missing.append(f"public_law:{r['cite']}/s{sec} (fragment_selection_required)")
                elif include:
                    entry["_content"] = content
                rec["fragments"].append(entry)
            whole_rels = sorted({x["relationship"] for x in refs if x["cite"] == r["cite"] and not x["pl_section"]}, key=R.PRECEDENCE.index)
            if set(whole_rels) & R.REQUIRED and not is_cra:
                missing.append(f"public_law:{r['cite']} (needed as {whole_rels[0]} but cited as a whole law; no section can be selected)")
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
        cons = code.section(CRA_CONSEQUENCE[0], CRA_CONSEQUENCE[1], v["date"], R.SUPPORTING_CONTEXT) if rp else None
        if cons is not None:
            cons.pop("_bytes", None); cons["inclusion"] = R.CONTENT_INCLUDED; cons["basis"] = "fixed rule: the CRA consequence section in force at the vote"
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
    if packet is not None:
        ctx["metrics"] = packet["metrics"]; ctx["budget"] = packet["budget"]
    for rec in ctx["existing_law_context"]:
        rec.pop("_content", None); rec.pop("_bytes", None)
        for h in rec.get("hierarchy", []):
            h.pop("_content", None)
    for pl in ctx["public_laws"]:
        for fr_ in pl["fragments"]:
            fr_.pop("_content", None)
    if ctx["cra"]["consequence_source"]:
        ctx["cra"]["consequence_source"].pop("_content", None); ctx["cra"]["consequence_source"].pop("_bytes", None)
    ctx["official_summary"].pop("_text", None)
    return ctx, packet


def build_packet(b: dict, ctx: dict, xml_bytes: bytes, store: Store) -> dict:
    """Everything the Maker may cite, byte-exact from tracked artefacts."""
    v, tb, obj = b["vote"], b["text_binding"], b["object"]
    law, tracked = [], []
    for rec in ctx["existing_law_context"]:
        if rec["status"] == "fetched" and rec["inclusion"] == R.CONTENT_INCLUDED:
            law.append({"type": "us_code", "identifier": rec["identifier"], "section_identifier": rec["section_identifier"], "scope": rec["scope"],
                        "heading": rec["heading"], "as_of": rec["as_of"], "relationship": rec["relationship"], "relationships": rec["relationships"],
                        "cited_as": rec["cited_as"],
                        "inclusion": rec["inclusion"],
                        "hierarchy": [{"identifier": h["identifier"], "sha256": h["sha256"], "content": h["_content"]} for h in rec["hierarchy"]],
                        "sha256": rec["fragment_sha256"], "content": rec["_content"]})
        else:
            tracked.append({"type": "us_code", "identifier": rec["identifier"], "relationships": rec["relationships"], "inclusion": R.REFERENCE_TRACKED,
                            "as_of": rec.get("as_of"), "sha256": rec.get("fragment_sha256"), "content_included": False,
                            "note": "the measure's citation may be repeated as written; the provision's contents may not be described"})
    for pl in ctx["public_laws"]:
        for fr_ in pl["fragments"]:
            if fr_["status"] == "fetched" and fr_["inclusion"] == R.CONTENT_INCLUDED:
                law.append({"type": "public_law", "identifier": f"{pl['cite']}/s{fr_['section']}", "scope": "section",
                            "as_of": {"enacted_law": f"Public Law {pl['congress']}-{pl['law']}"}, "relationship": fr_["relationships"][0],
                            "relationships": fr_["relationships"], "inclusion": fr_["inclusion"], "hierarchy": [],
                            "sha256": fr_["fragment_sha256"], "content": fr_["_content"]})
            else:
                tracked.append({"type": "public_law", "identifier": f"{pl['cite']}/s{fr_['section']}", "relationships": fr_["relationships"],
                                "inclusion": R.REFERENCE_TRACKED, "sha256": fr_.get("fragment_sha256"), "content_included": False,
                                "note": "the measure's citation may be repeated as written; the provision's contents may not be described"})
    cited_laws = [{"type": "public_law", "identifier": pl["cite"], "sha256": pl["sha256"], "divisions": pl["divisions"], "relationships": pl["relationships"],
                   "inclusion": R.REFERENCE_TRACKED, "content_included": False,
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
    voted = xml_bytes.decode("utf8", "ignore")
    metrics = packet_metrics(voted, law, cra_packet, summary_packet, tracked, cited_laws)
    return {"packet_schema": PACKET_SCHEMA,
            "vote": {**v, "senator_votes_source": "block F / S119_votes.csv (not included here)"},
            "legislative_object": {"type": obj["type"], "id": obj["id"], "title": obj["title"], "short_title": obj["short_title"], "origin_chamber": obj["origin_chamber"]},
            "classification": {"kind": b["classification"]["kind"]},
            "receipt_scaffold": b["receipt"],
            "voted_text": {"version_code": tb["version_code"], "version_name": tb["version_name"], "date": tb["version_date"], "url": tb["govinfo_url"],
                           "sha256": tb["sha256"], "format": "govinfo-bill-xml", "content": voted},
            "existing_law_context": law, "tracked_references": tracked, "cited_public_laws_not_included": cited_laws,
            "official_summary": summary_packet, "cra_context": cra_packet,
            "completeness": ctx["completeness"], "generation": ctx["generation"],
            "metrics": metrics, "budget": budget_for(metrics),
            "maker_rules": ["factual claims only from the content fields of this packet", "no browsing, no retrieval, no model memory for facts",
                            "derived metadata (headings, relationships, statuses) is not source text",
                            "a tracked reference may be named as the measure names it; its contents may not be described",
                            "vote_result and next_step are fixed text: repeat them, do not restate a failed vote as advancing"]}


def packet_metrics(voted_text: str, law: list[dict], cra_packet: dict, summary_packet: dict, tracked: list[dict], cited_laws: list[dict]) -> dict:
    """Deterministic size figures for a packet: what the Maker would read."""
    ctx_chars = sum(len(e["content"]) + sum(len(h["content"]) for h in e["hierarchy"]) for e in law)
    cons = (cra_packet or {}).get("statutory_consequence_source")
    ctx_chars += len(cons["content"]) if cons else 0
    summ = len(summary_packet.get("content") or "")
    return {"voted_text_chars": len(voted_text), "context_chars": ctx_chars, "official_summary_chars": summ,
            "total_source_chars": len(voted_text) + ctx_chars + summ,
            "source_count": 1 + len(law) + (1 if cons else 0) + (1 if summ else 0),
            "included_context_fragment_count": len(law) + (1 if cons else 0),
            "hierarchy_fragment_count": sum(len(e["hierarchy"]) for e in law),
            "tracked_reference_count": len(tracked) + len(cited_laws)}


def budget_for(metrics: dict) -> dict:
    """A packet over the documented threshold is flagged for a person to confirm
    its size is necessary before any Maker reads it. Nothing is ever truncated."""
    over = metrics["total_source_chars"] > PACKET_REVIEW_CHARS
    return {"review_threshold_chars": PACKET_REVIEW_CHARS, "status": "REVIEW_REQUIRED" if over else "WITHIN_BUDGET",
            "rule": "no truncation; a packet over the threshold needs a recorded human review before generation"}


# ---- files and runner --------------------------------------------------------------

def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in ("history", "recorded_utc")}


def _digest(d: dict) -> dict:
    """What a packet's history keeps of a superseded packet: its hash and headline
    state. The superseded packet itself is in git; copying its sources into the
    new packet would make every change double the file."""
    return {"packet_sha256": sha256_bytes(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()), "packet_schema": d.get("packet_schema"),
            "generation": (d.get("generation") or {}).get("status"), "metrics": d.get("metrics"),
            "voted_text_sha256": (d.get("voted_text") or {}).get("sha256"),
            "law_sha256": [e.get("sha256") for e in d.get("existing_law_context", [])]}


def write_json(path: Path, doc: dict, digest_history: bool = False) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if path.exists():
        old = json.loads(path.read_text())
        if _strip(old) == _strip(doc):
            return "unchanged"
        hist = old.get("history", []); prev = _digest(_strip(old)) if digest_history else _strip(old); prev["superseded_utc"] = stamp; hist.append(prev)
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
            writes["packet_" + write_json(ppath, packet, digest_history=True)] += 1
        elif ppath.exists():
            ppath.unlink(); writes["packet_removed"] += 1
        gen[ctx["generation"]["status"]] += 1; comp[ctx["completeness"]["status"]] += 1
        rows.append((b["object"]["id"], b["vote"]["date"], ctx["generation"]["status"], ctx["completeness"]["status"], ctx["cra"]["mode"], ctx["cra"]["rule_status"],
                     ctx["official_summary"]["version_relationship"], len([x for x in ctx["existing_law_context"] if x["status"] == "fetched" and x.get("inclusion") == R.CONTENT_INCLUDED]), ctx["completeness"]["missing"][:2],
                     (ctx.get("metrics") or {}).get("total_source_chars"), (ctx.get("budget") or {}).get("status")))
    store.save()
    index = {"schema": CONTEXT_SCHEMA, "rule": {"section_cap": SECTION_CAP, "large_text_words": LARGE_TEXT_WORDS, "cra_consequence": "/us/usc/t5/s801",
                                                "full_section_max_chars": FULL_SECTION_MAX_CHARS, "packet_review_chars": PACKET_REVIEW_CHARS,
                                                "relationships": R.PRECEDENCE,
                                                "release_point_rule": "latest OLRC release point dated on or before the vote; never a later one"},
             "generation": dict(gen), "completeness": dict(comp),
             "votes": [{"measure": r[0], "date": r[1], "generation": r[2], "completeness": r[3], "cra_mode": r[4], "rule_status": r[5], "summary": r[6], "law_sections": r[7],
                        "total_source_chars": r[9], "budget": r[10]} for r in rows]}
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
