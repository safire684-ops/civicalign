"""Federal Register documents, resolved from a citation through the Office of
the Federal Register's own API (keyless). A citation "89 FR 71160" plus its
publication date identifies exactly one document start page; the API's
day listing is filtered by start page. Page-only citations are searched in a
date window derived from the volume year. Nothing is matched by title alone.
"""
import json
import re
import urllib.parse
from dataclasses import dataclass

API = "https://www.federalregister.gov/api/v1/documents.json"
FIELDS = ("document_number", "citation", "title", "type", "start_page", "end_page", "publication_date",
          "agencies", "html_url", "full_text_xml_url", "regulation_id_numbers", "docket_ids")


@dataclass(frozen=True)
class FrDocument:
    document_number: str
    citation: str
    title: str
    type: str
    publication_date: str
    agencies: tuple[str, ...]
    html_url: str
    full_text_xml_url: str | None
    start_page: int


def volume_year(volume: int) -> int:
    return 1935 + volume   # 89 FR = 2024, 90 FR = 2025


def query_url(params: dict, page: int = 1) -> str:
    q = [("per_page", "1000"), ("page", str(page))] + [("fields[]", f) for f in FIELDS]
    for k, v in params.items():
        if isinstance(v, list):
            q += [(k, x) for x in v]
        else:
            q.append((k, v))
    return API + "?" + urllib.parse.urlencode(q)


def day_params(day: str) -> dict:
    return {"conditions[publication_date][is]": day}


def window_params(start: str, end: str) -> dict:
    return {"conditions[publication_date][gte]": start, "conditions[publication_date][lte]": end,
            "conditions[type][]": ["RULE", "NOTICE", "PRORULE"]}


def parse_results(payload: bytes) -> tuple[list[FrDocument], int]:
    d = json.loads(payload)
    out = [FrDocument(r["document_number"], r.get("citation") or "", r.get("title") or "", r.get("type") or "",
                      r.get("publication_date") or "", tuple(a.get("name", "") for a in r.get("agencies", [])),
                      r.get("html_url") or "", r.get("full_text_xml_url"), int(r.get("start_page") or 0))
           for r in d.get("results", [])]
    return out, int(d.get("total_pages") or 1)


def match_citation(docs: list[FrDocument], volume: int, page: int) -> list[FrDocument]:
    return [x for x in docs if x.start_page == page and x.citation.startswith(f"{volume} FR ")]


def normalise(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def title_agrees(rule_title: str, doc_title: str) -> bool:
    a, b = normalise(rule_title), normalise(doc_title)
    return bool(a) and (a in b or b in a)


CITE = re.compile(r"(\d{2,3}) Fed\. Reg\. (\d{1,6})(?:[;,]?\s*(?:published )?\(?([A-Z][a-z]+ \d{1,2}, \d{4})\)?)?")


def citation_in(text: str) -> tuple[int, int, str | None] | None:
    m = CITE.search(text or "")
    if not m:
        return None
    from datetime import datetime
    day = datetime.strptime(m.group(3), "%B %d, %Y").strftime("%Y-%m-%d") if m.group(3) else None
    return int(m.group(1)), int(m.group(2)), day
