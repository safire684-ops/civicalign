"""The United States Code from the Office of the Law Revision Counsel, at a
dated release point.

OLRC republishes the Code after every Public Law that changes it. Each release
point (e.g. "119-18", dated 2025-06-12) offers one USLM XML archive per title
with stable identifiers (/us/usc/t8/s1226, /us/usc/t8/s1226/c/1). That is the
only official, keyless, point-in-time source of statutory text, so it is what
CivicAlign binds "existing law" to. Release points before the current Congress
are listed but not downloadable in this form; a vote that needs one cannot be
given context (no inference, no fallback to today's law).
"""
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

PRIOR_URL = "https://uscode.house.gov/download/priorreleasepoints.htm"
CURRENT_URL = "https://uscode.house.gov/download/download.shtml"
RP_PAGE_URL = "https://uscode.house.gov/download/releasepoints/us/pl/{congress}/{law}/usc-rp@{congress}-{law}.htm"
CLASSIFICATION_URL = "https://uscode.house.gov/classification/tbl{congress}pl_{session}.htm"
ARCHIVE_URL = "https://uscode.house.gov/download/releasepoints/us/pl/{congress}/{law}/xml_usc{title}@{congress}-{law}.zip"


@dataclass(frozen=True)
class ReleasePoint:
    congress: int
    law: int
    date: date

    @property
    def label(self) -> str:
        return f"{self.congress}-{self.law}"


def parse_release_points(html: str) -> list[ReleasePoint]:
    pts = {(int(c), int(n), datetime.strptime(d, "%m/%d/%Y").date())
           for c, n, d in re.findall(r"Public Law (\d+)-(\d+)\s*\((\d{2}/\d{2}/\d{4})\)", html)}
    return sorted((ReleasePoint(c, n, d) for c, n, d in pts), key=lambda p: (p.date, p.congress, p.law))


def in_force(points: list[ReleasePoint], vote_date: str) -> ReleasePoint | None:
    """The latest release point dated on or before the vote: the Code as it
    stood when the Senate voted. A release point that would already contain the
    measure itself can never be selected, because it is dated after the vote."""
    d = date.fromisoformat(vote_date)
    prior = [p for p in points if p.date <= d]
    return prior[-1] if prior else None


def title_code(cite_title: str) -> str:
    """'8' -> '08', '50' -> '50', '5a' (appendix) -> '05a'."""
    m = re.match(r"(\d+)([a-z]?)$", cite_title)
    if not m:
        raise ValueError(f"unrecognised title {cite_title!r}")
    return f"{int(m.group(1)):02d}{m.group(2)}"


def archive_name(cite_title: str, rp: ReleasePoint) -> str:
    return f"xml_usc{title_code(cite_title)}@{rp.label}.zip"


def archive_url(cite_title: str, rp: ReleasePoint) -> str:
    return ARCHIVE_URL.format(congress=rp.congress, law=rp.law, title=title_code(cite_title))


def read_title(zip_path: Path) -> bytes:
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".xml")]
        if len(names) != 1:
            raise ValueError(f"{zip_path.name}: expected one XML member, found {names}")
        return z.read(names[0])


def publication_name(title_xml: bytes) -> str:
    m = re.search(rb"<docPublicationName>(.*?)</docPublicationName>", title_xml[:5000])
    return m.group(1).decode() if m else ""


_OPEN = re.compile(rb"<(/?)section\b[^>]*?(/?)>")


def extract_section(title_xml: bytes, identifier: str) -> bytes | None:
    """The byte-exact <section identifier="…"> … </section> element, found by
    balanced tag scanning so nested sections do not truncate it."""
    # OLRC writes hyphenated section numbers with an en-dash (s80a\u20131); GovInfo
    # citations use a hyphen (80a-1). Either spelling identifies the same section.
    m = None
    for ident in (identifier, identifier.replace("-", "\u2013")):
        m = re.search(rb'<section[^>]*identifier="' + re.escape(ident.encode("utf8")) + rb'"[^>]*>', title_xml)
        if m:
            break
    if not m:
        return None
    start, depth = m.start(), 0
    for tag in _OPEN.finditer(title_xml, start):
        if tag.group(2) == b"/":
            continue
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return title_xml[start:tag.end()]
    return None


USLM_LEVELS = (b"subsection", b"paragraph", b"subparagraph", b"clause", b"subclause", b"item", b"subitem")


def _element_at(xml: bytes, start: int, tag: bytes) -> bytes | None:
    """The balanced <tag …> … </tag> element that opens at `start`."""
    pat = re.compile(rb"<(/?)" + re.escape(tag) + rb"\b[^>]*?(/?)>")
    depth = 0
    for t in pat.finditer(xml, start):
        if t.group(2) == b"/":
            if depth == 0:
                return xml[start:t.end()]
            continue
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return xml[start:t.end()]
    return None


def extract_node(section_xml: bytes, identifier: str) -> tuple[bytes, str] | None:
    """A sub-section node (subsection, paragraph, …) by its USLM identifier,
    byte-exact from the already extracted section, e.g. /us/usc/t8/s1182/a/2.
    Returns (bytes, tag) or None."""
    for ident in (identifier, identifier.replace("-", "\u2013")):
        m = re.search(rb'<(' + b"|".join(USLM_LEVELS) + rb')\b[^>]*identifier="' + re.escape(ident.encode("utf8")) + rb'"[^>]*>', section_xml)
        if m:
            el = _element_at(section_xml, m.start(), m.group(1))
            return (el, m.group(1).decode()) if el is not None else None
    return None


def lead_in(element_xml: bytes) -> bytes:
    """The part of a provision before its first lower-level provision: its number,
    heading and chapeau. For an ancestor of a cited node this is the context a
    reader needs to know what the node belongs to. Byte-exact prefix."""
    first = re.search(rb"<(?:" + b"|".join(USLM_LEVELS) + rb")\b[^>]*identifier=", element_xml[1:])
    return element_xml[: first.start() + 1] if first else element_xml


def section_heading(section_xml: bytes) -> str:
    m = re.search(rb"<heading[^>]*>(.*?)</heading>", section_xml, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1).decode("utf8", "ignore"))).strip() if m else ""


def usc_identifier(cite: str) -> tuple[str, str, str] | None:
    """'usc/8/1226' -> ('8', '1226', '/us/usc/t8/s1226')."""
    m = re.match(r"usc/(\d+[a-z]?)/([0-9A-Za-z\-\.]+)$", cite)
    if not m:
        return None
    return m.group(1), m.group(2), f"/us/usc/t{m.group(1)}/s{m.group(2)}"


def archives_listed(rp_page_html: str, rp: "ReleasePoint") -> set[str]:
    """Archive file names a release point's page links. Some release points
    exist in the list but publish nothing; their pages carry no archive links."""
    return set(re.findall(r"xml_usc[0-9A-Za-z]+@" + re.escape(rp.label) + r"\.zip", rp_page_html))


def parse_classification(text: str) -> dict[str, set[tuple[str, str]]]:
    """OLRC's classification table for a Congress: one line per affected Code
    provision, 'title  section  status  PL  law-section  page'. Returns
    {'119-26': {('21', '801'), …}}. Only what the table states; nothing inferred."""
    out: dict[str, set[tuple[str, str]]] = {}
    plain = re.sub(r"<[^>]+>", " ", text)
    for line in plain.splitlines():
        m = re.match(r"\s*(\d+[a-z]?)\s+(\S+)\s+.*?\b(\d{2,3}-\d+)\b", line)
        if not m:
            continue
        out.setdefault(m.group(3), set()).add((m.group(1), m.group(2).replace("\u2013", "-")))
    return out


def in_force_for_section(points: list["ReleasePoint"], published: dict[str, set[str]], classification: dict[str, set[tuple[str, str]]],
                         vote_date: str, cite_title: str, section: str) -> dict:
    """The archive that holds a section exactly as in force at the vote.

    Take the latest release point on or before the vote whose archive for the
    title is published. Every release point between it and the vote is an
    enacted law whose archive is not published; the section is confirmed in
    force only if OLRC's classification table shows none of those laws affected
    the section (or the title, when a law's entries are absent). Otherwise the
    result is ambiguous. Nothing later than the vote is ever used."""
    d = date.fromisoformat(vote_date)
    prior = [p for p in points if p.date <= d]
    if not prior:
        return {"status": "no_release_point"}
    name = None
    chosen = None
    for p in reversed(prior):
        n = f"xml_usc{title_code(cite_title)}@{p.label}.zip"
        if n in published.get(p.label, set()):
            chosen, name = p, n
            break
    if chosen is None:
        return {"status": "no_published_archive", "latest_release_point": prior[-1].label}
    intervening = [p for p in prior if p.date > chosen.date]
    affected = []
    for p in intervening:
        entries = classification.get(p.label)
        if entries is None:
            affected.append(f"{p.label} (not in classification table)")
        elif (cite_title, section.replace("\u2013", "-")) in entries or any(t == cite_title and s.startswith(section.replace("\u2013", "-") + "(") for t, s in entries):
            affected.append(p.label)
    return {"status": "ambiguous" if affected else "ok", "release_point": chosen, "archive": name,
            "intervening": [p.label for p in intervening], "affected_by": affected,
            "check": "OLRC classification table" if intervening else "no intervening release point"}
