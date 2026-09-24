"""Why each cited provision is (or is not) in a source packet.

THE PRINCIPLE: the Maker gets the minimum official context necessary to
understand the measure's direct change. A citation's relationship to the measure
is read from where it sits in the voted XML, never from a model:

  AMENDED_TARGET            the measure inserts into, adds to or redesignates within it
  REPLACED_TEXT             the measure strikes, repeals or rewrites its existing text
  DEFINITION_REQUIRED       it sits inside one of the measure's own definitions, or the
                            measure imports a definition from it ("as defined in")
  CROSS_REFERENCE_REQUIRED  an operative provision applies it as a test or acts under it
                            ("described in", "inadmissible under", "pursuant to section …");
                            also the default when no rule below matches (fail closed)
  CROSS_REFERENCE_ONLY      it only names a program, system, agreement or fund by its
                            statutory address ("the … system under section …"), or it
                            cites an Act or chapter as a whole ("et seq.", a whole
                            Public Law or division)
  SUPPORTING_CONTEXT        not cited by the measure; added by a fixed CivicAlign rule
                            (5 U.S.C. 801 for Congressional Review Act resolutions)

The first four put the cited provision's text in the packet
(CONTENT_INCLUDED_FOR_GENERATION): the exact node the citation names ("8 U.S.C.
1182(a)(2)" is paragraph (a)(2), not all of section 1182), with the headings and
lead-in of the provisions above it. CROSS_REFERENCE_ONLY is REFERENCE_TRACKED: the
citation and the in-force source hash are recorded, the text is not given to
the Maker, and the Maker may not describe it.

A statutory citation the XML does not tag, or a tagged citation whose visible
text names more provisions than its structured cite, cannot be resolved
deterministically. Such gaps are detected here (a pattern match used ONLY to find
gaps, never to source content); in a location that needs content they hold the
context at SOURCE_CONTEXT_PENDING.
"""
import hashlib
import io
import re
import xml.etree.ElementTree as ET

from ..sources import publaw

AMENDED_TARGET = "AMENDED_TARGET"
REPLACED_TEXT = "REPLACED_TEXT"
DEFINITION_REQUIRED = "DEFINITION_REQUIRED"
CROSS_REFERENCE_REQUIRED = "CROSS_REFERENCE_REQUIRED"
CROSS_REFERENCE_ONLY = "CROSS_REFERENCE_ONLY"
SUPPORTING_CONTEXT = "SUPPORTING_CONTEXT"
PRECEDENCE = [AMENDED_TARGET, REPLACED_TEXT, DEFINITION_REQUIRED, CROSS_REFERENCE_REQUIRED, SUPPORTING_CONTEXT, CROSS_REFERENCE_ONLY]
REQUIRED = frozenset({AMENDED_TARGET, REPLACED_TEXT, DEFINITION_REQUIRED, CROSS_REFERENCE_REQUIRED, SUPPORTING_CONTEXT})

CONTENT_INCLUDED = "CONTENT_INCLUDED_FOR_GENERATION"
REFERENCE_TRACKED = "REFERENCE_TRACKED"

LEVELS = ("section", "subsection", "paragraph", "subparagraph", "clause", "subclause", "item", "subitem")
BLOCKS = set(LEVELS) | {"text", "quoted-block", "resolution-body", "legis-body"}

AMENDATORY = re.compile(r"\bis amended\b|\bare amended\b|\bis repealed\b|\bby striking\b|\bby inserting\b|\bis redesignated\b|\bare redesignated\b|\bby adding\b")
REPLACING = re.compile(r"\bis repealed\b|\bare repealed\b|\bby striking\b|\bto read as follows\b")
DEFINITION_HEADER = re.compile(r"\bdefin(?:ed|ition|itions)\b", re.I)
IMPORTS_DEFINITION = re.compile(r"(?:as defined in|has the meaning given (?:such term |that term |the term )?in|have the meanings? given (?:such terms |those terms )?in|within the meaning of)$", re.I)
# a program, system, agreement or fund named by its statutory home: the text identifies it, it does not apply it
NAMES_AN_INSTRUMENT = re.compile(r"\b(?:system|program|programs|agreement|agreements|fund|account|office|grant|grants|contract|contracts)"
                                 r"\s+(?:in effect\s+)?(?:under|established (?:by|under)|authorized (?:by|under)|carried out under)$", re.I)
APPLIES_A_TEST = re.compile(r"(?:described in|inadmissible under|deportable under|in compliance with|eligible (?:under|for)|requirements of|"
                            r"in accordance with|subject to|pursuant to|provided in|specified in|referred to in|under)$", re.I)
# trailing designation words stripped to reach the phrase that governs the citation
_DESIGNATION = re.compile(r"(?:\(|\)|,|;|\bof\b|\bor\b|\band\b|\bsections?\b|\bsubsections?\b|\bparagraphs?\b|\bsubparagraphs?\b|\bclauses?\b|"
                          r"\btitles?\b|\bparts?\b|\bchapters?\b|\bdivisions?\b|\bsubtitles?\b|\bsuch Act\b|\bthis Act\b|\bthat Act\b|"
                          r"\([0-9A-Za-z]+\)|[0-9][0-9A-Za-z\-–.]*|\bthe (?:(?:[A-Z0-9][\w'’,.\-–]*|and|of|the|for|to|on|in)\s+)*?(?:Act|Code|Resolution)(?: of \d{4})?)\s*$")
USC_DISPLAY = re.compile(r"^(?P<title>\d+[a-zA-Z]?)\s+U\.S\.C\.\s+(?P<section>[0-9A-Za-z\-–.]+?)(?P<pin>(?:\([0-9A-Za-z]+\))*)(?P<etseq>\s+et\.?\s*seq\.?)?\s*$")
SECTION_DISPLAY = re.compile(r"^[Ss]ection\s+(?P<section>[0-9A-Za-z\-–.]+?)(?P<pin>(?:\([0-9A-Za-z]+\))*)(?P<etseq>)$")
CONTINUES_LIST = re.compile(r"^(?:(?:,\s*|,?\s+or\s+|,?\s+and\s+)[0-9][0-9A-Za-z\-\u2013.()]*(?![0-9A-Za-z\-\u2013.()]|\s+U\.S\.C\.))+")
UNTAGGED_USC = re.compile(r"\d+[a-zA-Z]?\s+U\.S\.C\.\s+[0-9A-Za-z\-–.()]+(?:(?:,\s*|,?\s+or\s+|,?\s+and\s+)[0-9][0-9A-Za-z\-–.()]*(?![0-9A-Za-z\-–.()]|\s+U\.S\.C\.))*")


def _norm(s: str) -> str:
    return " ".join(s.split())


def _text_before(block: ET.Element, target: ET.Element) -> str:
    """Document-order text of `block` up to (not including) `target`."""
    out: list[str] = []

    def walk(el) -> bool:
        if el is target:
            return True
        out.append(el.text or "")
        for ch in el:
            if walk(ch):
                return True
            out.append(ch.tail or "")
        return False
    walk(block)
    return _norm("".join(out))


def governing_phrase(before: str) -> str:
    """Strip the designation ("section 202 of the National Emergencies Act (")
    from the end of the text before a citation, leaving the words that govern it."""
    s = before.rstrip()
    while True:
        m = _DESIGNATION.search(s)
        if not m or m.start() == len(s):
            return s
        s = s[:m.start()].rstrip()


def parse_display(display: str, parsable_cite: str) -> dict:
    """The citation's visible text, checked against its structured cite: pinpoint
    ("(a)(2)"), scope (node / section / act_as_a_whole), or `unparsed` when the
    visible text names more than the structured cite ("8 U.S.C. 1226, 1231(a), or 1357")."""
    m = USC_DISPLAY.match(_norm(display)) or SECTION_DISPLAY.match(_norm(display))
    cite = re.match(r"usc/(\d+[a-zA-Z]?)/([0-9A-Za-z\-\.]+)$", parsable_cite or "")
    if not m or not cite or (m.groupdict().get("title") and m.group("title").lower() != cite.group(1).lower()) \
            or m.group("section").replace("–", "-") != cite.group(2):
        return {"scope": "unparsed", "pinpoint": [], "display_matches_cite": False}
    pin = re.findall(r"\(([0-9A-Za-z]+)\)", m.group("pin") or "")
    if m.group("etseq"):
        return {"scope": "act_as_a_whole", "pinpoint": [], "display_matches_cite": True}
    return {"scope": "node" if pin else "section", "pinpoint": pin, "display_matches_cite": True}


def _ancestors(el, parent) -> list[ET.Element]:
    out, p = [], parent.get(el)
    while p is not None:
        out.append(p); p = parent.get(p)
    return out


def _location(anc: list[ET.Element]) -> dict:
    """Where a piece of text sits, given its enclosing elements innermost first."""
    path = [f"{a.tag}:{_norm(a.findtext('enum') or '')}" for a in reversed(anc) if a.tag in LEVELS]
    in_quote = any(a.tag in ("quoted-block", "quote") for a in anc)
    definition = None
    for a in anc:
        if a.tag not in LEVELS and a.tag != "quoted-block":
            continue
        hdr = _norm("".join(a.find("header").itertext())) if a.find("header") is not None else ""
        own_text = a.find("text")
        if DEFINITION_HEADER.search(hdr):
            definition = f"{a.tag} {_norm(a.findtext('enum') or '')} {hdr}".strip(); break
        if own_text is not None and own_text.find("term") is not None:
            definition = f"{a.tag} {_norm(a.findtext('enum') or '')} defines {_norm(''.join(own_text.find('term').itertext()))}".strip(); break
    block = next((a for a in anc if a.tag in BLOCKS), None)
    return {"path": path, "in_quoted_text": in_quote, "definition": definition, "block": block}


def classify(before: str, block_text: str, loc: dict, scope: str, legal_doc: str) -> tuple[str, str]:
    """(relationship, basis) by fixed precedence."""
    if not loc["in_quoted_text"] and AMENDATORY.search(block_text):
        if REPLACING.search(block_text):
            return REPLACED_TEXT, "amendatory instruction that strikes, repeals or rewrites existing text"
        return AMENDED_TARGET, "amendatory instruction that inserts, adds or redesignates"
    if scope == "act_as_a_whole":
        return CROSS_REFERENCE_ONLY, "cites an Act or chapter as a whole (et seq.)"
    if scope == "whole_law":
        return CROSS_REFERENCE_ONLY, "cites a Public Law or division as a whole"
    if loc["definition"]:
        return DEFINITION_REQUIRED, f"inside the measure's definition ({loc['definition']})"
    gov = governing_phrase(before)
    if IMPORTS_DEFINITION.search(gov):
        return DEFINITION_REQUIRED, f"imports a definition ({IMPORTS_DEFINITION.search(gov).group(0)!r})"
    if NAMES_AN_INSTRUMENT.search(gov):
        return CROSS_REFERENCE_ONLY, f"names an instrument by its statutory home ({NAMES_AN_INSTRUMENT.search(gov).group(0)!r})"
    m = APPLIES_A_TEST.search(gov)
    if m:
        return CROSS_REFERENCE_REQUIRED, f"operative provision applies or acts under it ({m.group(0)!r})"
    return CROSS_REFERENCE_REQUIRED, "operative reference with no narrower rule (fail closed: content required)"


def _pl_parts(cite: str, block_text: str) -> tuple[str | None, str | None]:
    """A Public Law citation's section ("section 100051 of Public Law 119-21") or
    division ("division A of Public Law 119-4") from its enclosing provision."""
    pl = publaw.parse_cite(cite)
    if not pl:
        return None, None
    for m in publaw.SECTION_OF_PL.finditer(block_text):
        if (int(m.group(2)), int(m.group(3))) == pl:
            return m.group(1), None
    for m in publaw.DIVISION_OF_PL.finditer(block_text):
        if (int(m.group(2)), int(m.group(3))) == pl:
            return None, m.group(1)
    return None, None


def node_identifier(title: str, section: str, pinpoint: list[str]) -> str:
    return f"/us/usc/t{title}/s{section}" + "".join(f"/{p}" for p in pinpoint)


# ---- fallback: explicit U.S. Code citations the XML leaves untagged ---------------
#
# Structured external-xref citations are always preferred. This narrow grammar
# covers only the two forms found in voted texts, and only when the whole
# parenthetical matches it; anything else stays an unresolved gap:
#   R1  "(8 U.S.C. 1325 or 1326)"                 one title, a list of sections
#   R2  "(<xref>8 U.S.C. 1226</xref>, 1231(a), or 1357)"
#                                                  a tagged citation whose list continues
#                                                  untagged; the title is inherited from it
#   REF = a section number (digits, then at most three lower-case letters; no
#         dashes, so no ranges or hyphenated numbers) with optional explicit
#         pinpoints "(a)(1)"; separators ", ", " or ", " and ", ", or ", ", and ".
# Vague references ("that section", "this chapter", "applicable law"), "et seq.",
# "note", "App.", chapter citations, ranges and mixed titles are never resolved.
_REF = r"[0-9]+[a-z]{0,3}(?:\([0-9A-Za-z]{1,4}\))*"
_SEP = r"(?:,\s+or\s+|,\s+and\s+|\s+or\s+|\s+and\s+|,\s+)"
FALLBACK_R1 = re.compile(r"\((?P<title>[0-9]{1,2}) U\.S\.C\. (?P<refs>" + _REF + "(?:" + _SEP + _REF + r")*)\)")
FALLBACK_R2 = re.compile(r"(?P<refs>(?:" + _SEP + _REF + r")+)\)")
RULE_R1 = "R1: parenthetical of one title and a list of sections"
RULE_R2 = "R2: list continuing after a tagged citation; title inherited from its structured cite"


def _clean(text: str) -> str:
    """Trailing punctuation off a citation's text, keeping a pinpoint's own ")"."""
    t = _norm(text).rstrip(".;,")
    while t.endswith(")") and t.count(")") > t.count("("):
        t = t[:-1].rstrip(".;,")
    return t


def split_refs(refs: str) -> list[tuple[str, list[str]]]:
    """'1226, 1231(a), or 1357' -> [('1226', []), ('1231', ['a']), ('1357', [])]."""
    out = []
    for m in re.finditer(_REF, refs):
        out.append((re.match(r"[0-9]+[a-z]{0,3}", m.group(0)).group(0), re.findall(r"\(([0-9A-Za-z]+)\)", m.group(0))))
    return out


def _container(anc: list[ET.Element]) -> dict:
    holder = next((a for a in anc if a.get("id")), None)
    return {"tag": anc[0].tag if anc else None, "id": holder.get("id") if holder is not None else None,
            "id_on": holder.tag if holder is not None else None}


def _fallback_ref(title, section, pins, rule, fragment, sha, loc, rel, basis, container, part, start, end) -> dict:
    return {"legal_doc": "usc", "cite": f"usc/{title}/{section}", "text": f"{title} U.S.C. {section}" + "".join(f"({p})" for p in pins),
            "location": loc["path"], "in_quoted_text": loc["in_quoted_text"], "scope": "node" if pins else "section", "pinpoint": pins,
            "display_matches_cite": True, "relationship": rel, "basis": basis, "pl_section": None, "pl_division": None,
            "source": "fallback_explicit_usc", "rule": rule, "source_fragment": fragment, "source_sha256": sha,
            "container": container, "text_part": part, "char_start": start, "char_end": end}


def analyse(xml_bytes: bytes) -> dict:
    """Every tagged citation with its location, scope and relationship; the
    statutory citations the XML leaves untagged or only partly structured (one
    gap per citation group); and, for groups the narrow fallback grammar
    recognises, the explicit citations it recovers, with full provenance."""
    root = ET.parse(io.BytesIO(xml_bytes)).getroot()
    parent = {c: p for p in root.iter() for c in p}
    sha = hashlib.sha256(xml_bytes).hexdigest()
    refs, gaps, fallback = [], [], []
    for x in root.iter("external-xref"):
        ld, cite = x.get("legal-doc", ""), x.get("parsable-cite", "")
        display = _norm("".join(x.itertext()))
        anc = _ancestors(x, parent)
        loc = _location(anc)
        block = loc["block"]
        block_text = _norm("".join(block.itertext())) if block is not None else ""
        before = _text_before(block, x) if block is not None else ""
        if ld == "usc":
            d = parse_display(display, cite)
        elif ld == "public-law":
            pl_section, pl_division = _pl_parts(cite, block_text)
            d = {"scope": "section" if pl_section else "whole_law", "pinpoint": [pl_section] if pl_section else [],
                 "display_matches_cite": True, "pl_section": pl_section, "pl_division": pl_division}
        else:
            d = {"scope": "unparsed", "pinpoint": [], "display_matches_cite": False}
        rel, basis = classify(before, block_text, loc, d["scope"], ld)
        refs.append({"legal_doc": ld, "cite": cite, "text": display, "location": loc["path"], "in_quoted_text": loc["in_quoted_text"],
                     "scope": d["scope"], "pinpoint": d["pinpoint"], "display_matches_cite": d["display_matches_cite"],
                     "relationship": rel, "basis": basis, "pl_section": d.get("pl_section"), "pl_division": d.get("pl_division"),
                     "source": "structured_xref"})
        cont = CONTINUES_LIST.match(x.tail or "")
        if ld == "usc" and cont:
            gap = {"kind": "citation_list_continues_untagged", "text": _clean(display + cont.group(0)), "cite": cite, "location": loc["path"],
                   "relationship": rel, "basis": basis, "provisions": [], "untagged_provisions": [], "resolved": False, "rule": None}
            r2 = FALLBACK_R2.match(x.tail or "")
            title = (cite.split("/") + ["", ""])[1]
            if r2 and before.endswith("(") and d["display_matches_cite"] and d["scope"] in ("section", "node") and re.fullmatch(r"[0-9]{1,2}", title):
                fragment = "(" + display + r2.group(0)
                gap["provisions"] = [display] + [f"{title} U.S.C. {sec}" + "".join(f"({p})" for p in pins) for sec, pins in split_refs(r2.group("refs"))]
                gap["untagged_provisions"] = gap["provisions"][1:]
                gap.update({"resolved": True, "rule": RULE_R2})
                for sec, pins in split_refs(r2.group("refs")):
                    fallback.append(_fallback_ref(title, sec, pins, RULE_R2, fragment, sha, loc, rel, basis, _container(anc),
                                                  "tail of external-xref", 0, r2.end()))
            gaps.append(gap)
        if ld == "usc" and not d["display_matches_cite"]:
            gaps.append({"kind": "citation_text_not_parsed", "text": display, "cite": cite, "location": loc["path"],
                         "relationship": rel, "basis": basis, "provisions": [], "untagged_provisions": [], "resolved": False, "rule": None})
    # untagged "N U.S.C. …" citations: text directly inside an element (its .text) or
    # after it inside its parent (its .tail), never the text of an external-xref itself
    for el in root.iter():
        chunks = [] if el.tag == "external-xref" else [(el.text, [el] + _ancestors(el, parent), "text")]
        if parent.get(el) is not None:
            chunks.append((el.tail, _ancestors(el, parent), f"tail of {el.tag}"))
        for chunk, anc, part in chunks:
            for m in UNTAGGED_USC.finditer(chunk or ""):
                loc = _location(anc)
                block_text = _norm("".join(loc["block"].itertext())) if loc["block"] is not None else ""
                rel, basis = classify(_norm(chunk[:m.start()]), block_text, loc, "section", "usc")
                gap = {"kind": "untagged_citation", "text": _clean(m.group(0)), "cite": None, "location": loc["path"],
                       "relationship": rel, "basis": basis, "provisions": [], "untagged_provisions": [], "resolved": False, "rule": None}
                r1 = FALLBACK_R1.match(chunk, m.start() - 1) if m.start() > 0 else None
                if r1:
                    title = r1.group("title")
                    gap["provisions"] = gap["untagged_provisions"] = [f"{title} U.S.C. {sec}" + "".join(f"({p})" for p in pins) for sec, pins in split_refs(r1.group("refs"))]
                    gap.update({"resolved": True, "rule": RULE_R1})
                    for sec, pins in split_refs(r1.group("refs")):
                        fallback.append(_fallback_ref(title, sec, pins, RULE_R1, r1.group(0), sha, loc, rel, basis, _container(anc), part, r1.start(), r1.end()))
                gaps.append(gap)
    return {"references": refs + fallback, "gaps": gaps}
