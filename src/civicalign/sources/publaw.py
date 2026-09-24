"""Enacted Public Laws from GovInfo, as USLM XML (the plain-XML path returns an
HTML page). A bill that cites "section 100051 of Public Law 119-21" gets that
section extracted by its USLM identifier; a bill that cites a whole law or a
division ("division F of Public Law 118-47") gets the law identified and
hashed, but no section is extracted, because nothing narrower is deterministic.
"""
import re

URL = "https://www.govinfo.gov/content/pkg/PLAW-{congress}publ{law}/uslm/PLAW-{congress}publ{law}.xml"


def law_url(congress: int, law: int) -> str:
    return URL.format(congress=congress, law=law)


def parse_cite(cite: str) -> tuple[int, int] | None:
    m = re.match(r"pl/(\d+)/(\d+)$", cite)
    return (int(m.group(1)), int(m.group(2))) if m else None


def looks_like_uslm(data: bytes) -> bool:
    head = data[:600].lower()
    return head.startswith(b"<?xml") and b"<html" not in head


_OPEN = re.compile(rb"<(/?)section\b[^>]*?(/?)>")


def extract_section(law_xml: bytes, section_number: str) -> bytes | None:
    """The <section> whose identifier ends in /s<number> (USLM), or whose
    <num value="…"> equals it; balanced-scanned so nested sections are kept."""
    pats = [rb'<section[^>]*identifier="[^"]*/s' + re.escape(section_number.encode()) + rb'"[^>]*>',
            rb'<section[^>]*>\s*<num[^>]*value="' + re.escape(section_number.encode()) + rb'"']
    m = None
    for p in pats:
        m = re.search(p, law_xml)
        if m:
            break
    if not m:
        return None
    start, depth = m.start(), 0
    for tag in _OPEN.finditer(law_xml, start):
        if tag.group(2) == b"/":
            continue
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return law_xml[start:tag.end()]
    return None


SECTION_OF_PL = re.compile(r"section (\d+[A-Za-z\-]*)(?:\([a-z0-9]+\))* of (?:the |such )?(?:[A-Z][^,;]{0,80}\()?Public Law (\d+)[–-](\d+)")
DIVISION_OF_PL = re.compile(r"(division [A-Z]|title [IVXLC]+) of Public Law (\d+)[–-](\d+)", re.I)
