"""Pillars 4-6: the page builder and the three views (Step 4), published to demo/ (Step 5A).

The builder reads only the saved result record, the methodology registry, the
saved anchors and the official committee names. These tests check the data it
embeds, the committed published pages in demo/, and what the pages must never
contain. Nothing here writes to data/ideology/ or demo/."""
import ast
import copy
import dataclasses
import json
import re
import shutil
from pathlib import Path

import pytest

from civicalign import build_pages as BP
from civicalign.config import DEFAULT
from civicalign.ideology import anchors as A
from civicalign.ideology import compute as C
from civicalign.ideology import ingest as I
from civicalign.ideology import methodology as M
from civicalign.ideology.store import Table

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "src" / "civicalign" / "templates" / "senator-check.template.html").read_text()


@pytest.fixture(scope="module")
def data():
    try:
        return BP.payload(DEFAULT)
    except BP.BuildError as e:
        pytest.skip(f"no saved result to build from: {e}")


@pytest.fixture(scope="module")
def pages():
    return BP.build(DEFAULT)


def numbers(obj):
    """Every displayed number in the payload (dicts carrying a registry id)."""
    if isinstance(obj, dict):
        if "m" in obj and "s" in obj:
            yield obj
        else:
            for v in obj.values():
                yield from numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from numbers(v)


def visible_text(page: str) -> str:
    return re.sub(r"<style>.*?</style>", " ", page, flags=re.S)


# ---- formatting ----------------------------------------------------------------------------

@pytest.mark.parametrize("value,decimals,signed,expected", [
    (0.3195, 3, False, "0.320"), (-0.216, 3, False, "−0.216"), (0.03675037944656569, 3, True, "+0.037"),
    (-0.3655, 3, True, "−0.366"), (0.0, 3, True, "0.000"), (-0.0001, 3, True, "0.000"), (0.2911, 2, False, "0.29"),
    (100, None, False, "100")])
def test_fmt_rounds_half_up_with_a_true_minus_sign(value, decimals, signed, expected):
    assert BP.fmt(value, decimals, signed) == expected


@pytest.mark.parametrize("raw,expected", [
    ("MCCONNELL, Addison Mitchell (Mitch)", "Mitch McConnell"), ("KING, Angus Stanley, Jr.", "Angus King Jr."),
    ("BLUNT ROCHESTER, Lisa", "Lisa Blunt Rochester"), ("HYDE-SMITH, Cindy", "Cindy Hyde-Smith"),
    ("LUJÁN, Ben Ray", "Ben Luján"), ("JUSTICE, James Conley, II", "James Justice II")])
def test_display_names(raw, expected):
    assert BP.display_name(raw) == expected


def test_scale_labels_use_the_whole_surname():
    assert BP.surname("BLUNT ROCHESTER, Lisa") == "Blunt Rochester" and BP.surname("MCCORMICK, David Harold") == "McCormick"


# ---- every number has its methodology ----------------------------------------------------------

def test_every_displayed_number_carries_its_registry_entry(data):
    nums = list(numbers(data))
    assert len(nums) == 400 + 3 + 10 + 16 * 5 + 2 - 1   # Pillar 4 (100 x 4), anchors, Pillar 5, Pillar 6 (16 x 5 + two shared)
    for n in nums:
        e = M.REGISTRY[n["m"]]
        if n["s"] == "NOT_AVAILABLE":
            assert n["d"] is None and n["r"] and e["not_available"], n["p"]
        else:
            assert n["d"] == BP.fmt(n["v"], e["decimals"], e["id"] in BP.SIGNED), n["p"]
        if not n["p"].startswith("reference_anchors."):
            assert M.entry_for(n["p"])["id"] == n["m"]


def test_every_registry_entry_reaches_the_page_and_the_methodology(data, pages):
    assert {n["m"] for n in numbers(data)} == set(M.REGISTRY)
    assert set(data["methods"]) == set(M.REGISTRY)
    for eid in M.REGISTRY:
        assert f'id="{eid}"' in pages["methodology.html"], eid
        m = data["methods"][eid]
        assert m["sources"] and m["formula"] and m["transformation"] and m["versions"] and m["limitations"]


def test_the_page_only_shows_numbers_through_num(pages):
    script = TEMPLATE[TEMPLATE.index("<script>"):]
    assert not re.search(r"\d\.\d{2,}", script), "no data value is written into the template"
    assert "throw new Error('number without a methodology entry" in script
    shown = re.findall(r"esc\((\w+)\.d\)", script)
    assert set(shown) <= {"n", "md", "sm", "pl", "w"}, shown     # screen-reader text repeats numbers already shown by num()


def test_the_build_refuses_a_number_without_an_entry(monkeypatch):
    rec = BP.latest(DEFAULT)
    bad = copy.deepcopy(rec)
    bad["results"]["pillar5"]["new_quantity"] = {"value": 1.0, "status": "AVAILABLE", "units": "x", "reason": None}
    monkeypatch.setattr(BP, "latest", lambda cfg: bad)
    with pytest.raises(BP.BuildError, match="new_quantity"):
        BP.payload(DEFAULT)


def test_the_build_refuses_a_tampered_record_or_missing_anchors(tmp_path):
    cfg = dataclasses.replace(DEFAULT, ideology_dir=tmp_path / "ideology")
    shutil.copytree(DEFAULT.ideology_dir, cfg.ideology_dir, ignore=shutil.ignore_patterns("reference_anchors.jsonl"))
    with pytest.raises(A.AnchorError):
        BP.payload(cfg)
    f = next((cfg.ideology_dir / "metrics").glob("*.json"))
    f.write_text(f.read_text().replace('"value":0.204', '"value":0.999', 1))
    with pytest.raises(BP.BuildError, match="index hash"):
        BP.latest(cfg)


# ---- the three views ----------------------------------------------------------------------------

def test_pillar4_senators_and_exactly_three_labelled_anchors(data):
    states = data["p4"]["states"]
    assert len(states) == 50 and all(len(s["senators"]) == 2 for s in states)
    for s in states:
        for sen in s["senators"]:
            assert sen["state_on_senator_scale"]["s"] == "NOT_AVAILABLE" and sen["distance"]["s"] == "NOT_AVAILABLE"
            assert sen["state_public_estimate"]["se"] and sen["state_public_estimate"]["period"]
    a = data["p4"]["anchors"]
    assert [x["name"] for x in a] == ["Bernie Sanders", "Joe Biden", "JD Vance"]
    assert [x["score"]["d"] for x in a] == ["−0.546", "−0.314", "0.850"]
    assert a[1]["basis"].startswith("Senate voting record") and "not his presidency" in a[1]["basis"]
    assert a[2]["basis"].startswith("Senate voting record") and "not his vice presidency" in a[2]["basis"]
    assert "House" in a[0]["basis"] and "Senate" in a[0]["basis"]
    assert all(x["score"]["m"] == "p4.reference_anchor" for x in a)


def test_anchors_appear_only_in_pillar4(data):
    elsewhere = json.dumps({k: data[k] for k in ("p5", "p6")})
    assert "p4.reference_anchor" not in elsewhere and "Biden" not in elsewhere and "Vance" not in elsewhere


def test_pillar5_main_result_is_the_mean_and_medians_are_details_only(data):
    p5 = data["p5"]
    assert (p5["plain"]["m"], p5["weighted"]["m"], p5["diff"]["m"]) == ("p5.plain_mean", "p5.weighted_mean", "p5.weighting_difference")
    assert (p5["plain"]["d"], p5["weighted"]["d"], p5["diff"]["d"]) == ("0.120", "0.083", "+0.037")
    assert {p5[k]["m"] for k in ("median", "wmedian", "mdiff")} == {"p5.plain_median", "p5.weighted_median", "p5.median_difference"}
    assert p5["national"]["s"] == p5["gap"]["s"] == "NOT_AVAILABLE"
    # in the page, the medians are rendered only into the details block
    start = TEMPLATE.index("$('p5-medians')")
    uses = [m.start() for m in re.finditer(r"P5\.(median|wmedian|mdiff)\b", TEMPLATE)]
    assert len(uses) == 3 and all(start < u < start + 600 for u in uses)
    assert '<summary><span>Medians (secondary comparison)</span></summary>\n    <div id="p5-medians">' in TEMPLATE


def test_pillar5_plain_language_card():
    """The approved Pillar 5 wording (2026-09-25): title, three rows, explanation and "What does this mean?"."""
    start = TEMPLATE.index("// ================= Pillar 5")
    p5 = TEMPLATE[start:TEMPLATE.index("// ================= Pillar 6")]
    for text in ("Counting states vs. weighting by population", "Senate average", "Each senator counted equally",
                 "Population-weighted", "Difference",
                 "Every state gets two senators regardless of its population. Normally, each senator counts equally when "
                 "calculating the Senate average. If instead senators are weighted by the number of people their state "
                 "represents, the average changes from '+num(pl)+' to '+num(w)+'.",
                 "That is a difference of '+num(d)+'. ",
                 "population weighting moves the Senate average slightly toward the '+side+' side of Voteview’s −1 to +1 voting scale.",
                 "<summary><span>What does this mean?</span></summary>",
                 "Population weighting gives senators from larger states more weight and senators from smaller states less "
                 "weight. The two senators from the same state split that state’s population weight evenly.",
                 "This describes Senate voting records and state populations only. It does not tell us which laws passed, what "
                 "voters believe, or why Congress made a decision. This weighting method is still a CivicAlign candidate "
                 "method, not a final scientific standard."):
        assert text in p5, text
    # the side follows the sign of plain - weighted, so the words cannot contradict the numbers
    assert "var side=d.v>0?'liberal':'conservative';" in p5
    # the numbers in the card are the saved Pillar 5 main result, shown through num()
    assert "num(pl)" in p5 and "num(w)" in p5 and "num(d)" in p5
    for claim in ("because", "caused", "led to", "resulted in", "bill", "biased", "extreme", "unfair", "fair"):
        assert not re.search(rf"\b{claim}\b", p5, flags=re.I), claim


def test_pillar6_uses_only_committee_median_and_senate_drift(data):
    cs = data["p6"]["committees"]
    assert len(cs) == 16
    for c in cs:
        assert set(c) == {"code", "name", "official_name", "name_source", "name_retrieved", "listed", "scored", "left_out",
                          "committee_median", "committee_senate_drift", "committee_public_drift"}
        assert c["committee_public_drift"]["s"] == "NOT_AVAILABLE"
    ssap = next(c for c in cs if c["code"] == "SSAP")
    assert (ssap["committee_median"]["d"], ssap["committee_senate_drift"]["d"]) == ("−0.046", "−0.366")
    assert data["p6"]["senate_median"]["d"] == "0.320" and data["p6"]["national"]["s"] == "NOT_AVAILABLE"


def test_unavailable_values_say_why_on_the_page(data):
    na = [n for n in numbers(data) if n["s"] == "NOT_AVAILABLE"]
    assert na and all(M.REGISTRY[n["m"]]["not_available"] for n in na)
    assert "function why(n)" in TEMPLATE and "'<p class=\"why\">Why: '" in TEMPLATE
    assert "row(" in TEMPLATE and "+why(n)+" in TEMPLATE


# ---- what the pages never contain -------------------------------------------------------------------

def test_no_0_100_scale(pages):
    for name, page in pages.items():
        assert not re.search(r"\b0\s*(?:-|to|–)\s*100\b|/\s*100\b|display-scale|p100|\*\s*50\s*\+\s*50", page), name


def test_no_political_judgment_labels(pages):
    banned = (r"\b(extreme|extremist|moderate|centrist|radical|fringe|biased|good|bad|misaligned|aligned|out of step|"
              r"gatekeep\w*|obstruct\w*|blocked|betray\w*|defian\w*|ranking|ranked|representation score|representative score)\b")
    for name, page in pages.items():
        hits = re.findall(banned, visible_text(page), flags=re.I)
        assert not hits, (name, hits)


def test_no_engine_a_or_bill_content(pages):
    for name, page in pages.items():
        text = visible_text(page)
        for phrase in ("Recent votes", "recent vote", "receipt", "Yea", "Nay", "sent forward", "Yes / No", "sponsor",
                       "scorecard", "bill ideology", "liberal bill", "conservative bill", "Pillar 1", "Maker", "Checker"):
            assert phrase not in text, (name, phrase)


def test_the_builder_reads_only_engine_b_results():
    tree = ast.parse((ROOT / "src" / "civicalign" / "build_pages.py").read_text())
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mods += [(node.module or "")] + [a.name for a in node.names]
        elif isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
    forbidden = ("explain", "evaluation", "receipts", "billflow", "billstatus", "senate_votes", "pipeline", "peers",
                 "representation", "gatekeeping", "output_ideology", "landmarks", "whitepaper", "pillars", "inputs")
    assert not [m for m in mods if any(f in m for f in forbidden)], mods
    src = (ROOT / "src" / "civicalign" / "build_pages.py").read_text()
    assert "C.compute(" not in src and "_calculate" not in src, "the builder never recalculates"


# ---- Step 5A: the published pages, official committee names, Engine A separated -----------------------------

def test_published_pages_are_generated_by_the_new_builder(pages):
    assert BP.OUT == ROOT / "demo"
    for name, text in pages.items():
        f = ROOT / "demo" / name
        assert f.read_text() == text, f"demo/{name} is stale or not from build_pages: run python -m civicalign.build_pages"
    assert 'href="civicalign.css"' in pages["senator-check.html"] and 'href="civicalign.css"' in pages["methodology.html"]


def test_the_preview_folder_is_retired_and_templates_are_not_published():
    assert not (ROOT / "demo" / "next").exists(), "demo/next/ is no longer an output"
    assert "demo" + "/next" not in (ROOT / "src" / "civicalign" / "build_pages.py").read_text()
    assert not (ROOT / "demo" / "templates").exists(), "templates live in src/civicalign/templates/, outside the published folder"


def test_the_build_is_deterministic(pages):
    assert BP.build(DEFAULT) == pages


def test_committee_names_come_from_the_official_source(data):
    stored = {r["committee_id"]: r for r in Table(DEFAULT.ideology_dir, "committee_names").current()}
    for c in data["p6"]["committees"]:
        r = stored[c["code"]]
        assert (c["name"], c["official_name"]) == (r["display_name"], r["official_name"])
        assert c["official_name"] == "Senate Committee on " + c["name"] or c["official_name"] == "Senate Committee on the " + c["name"]
        assert c["name_source"] == I.COMMITTEE_LIST and r["source_url"].endswith("/committees-current.json") and not r["fixture"]


def test_no_fixed_committee_name_mapping_remains_in_the_builder():
    src = (ROOT / "src" / "civicalign" / "build_pages.py").read_text()
    assert "COMMITTEE_NAMES" not in src
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            assert not [k for k in keys if re.fullmatch(r"S[SL][A-Z]{2}", k)], keys
    assert not re.search(r"Agriculture|Appropriations|Judiciary|Armed Services", src)


def test_a_committee_without_an_official_name_stops_the_build(tmp_path):
    cfg = dataclasses.replace(DEFAULT, ideology_dir=tmp_path / "ideology")
    shutil.copytree(DEFAULT.ideology_dir, cfg.ideology_dir, ignore=shutil.ignore_patterns("committee_names.jsonl"))
    with pytest.raises(BP.BuildError, match="no official committee name"):
        BP.payload(cfg)


def test_engine_a_tests_no_longer_depend_on_the_pillars_4_6_page():
    for f in ("test_binding.py", "test_context.py", "test_evaluation.py"):
        text = (ROOT / "tests" / f).read_text()
        assert "senator-check.html" not in text and "methodology.html" not in text and "checks(run(" not in text, f
    assert "pillar1_checks" in (ROOT / "tests" / "test_binding.py").read_text()
    assert "pillar1_checks" in (ROOT / "tests" / "test_context.py").read_text()


def test_engine_b_calculations_are_unchanged():
    """Names and the page switch are not calculation inputs: the saved result is still current and reproducible."""
    src = (ROOT / "src" / "civicalign" / "ideology" / "compute.py").read_text()
    assert "committee_names" not in src and "reference_anchors" not in src
    assert C.plan(DEFAULT)["mode"] == "unchanged"
    assert C.verify(DEFAULT) == []


RETIRED_MODULES = ("alignment", "chamber", "committees", "space", "uncertainty", "peers", "representation", "gatekeeping",
                   "output_ideology", "landmarks", "export", "whitepaper", "build_demo", "sources/state_prefs", "sources/elections")


def test_the_retired_pillars_4_6_code_is_gone():
    """Step 5B removed the old Pillars 4-6 path; nothing may import it again."""
    for m in RETIRED_MODULES:
        assert not (ROOT / "src" / "civicalign" / f"{m}.py").exists(), m
    assert not (ROOT / "demo" / "methodology.template.html").exists()
    names = {m.split("/")[-1] for m in RETIRED_MODULES}
    for f in (ROOT / "src" / "civicalign").rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.ImportFrom):
                mods = [(node.module or "").split(".")[-1]] + [a.name for a in node.names]
                assert not (set(mods) & names), (f.name, set(mods) & names)


# ---- page guardrails carried over from the retired test_published_pages / test_perspective (Step 5B) --------

def _script():
    return TEMPLATE[TEMPLATE.index("<script>"):]


def test_every_drawn_track_is_hidden_from_screen_readers_and_described_in_text():
    s = _script()
    tracks = [m.start() for m in re.finditer(r"class=\"ctrack", s)]
    assert len(tracks) == 3, "one track per view"
    for i in tracks:
        assert s[i:i + 60].count('aria-hidden="true"') == 1, s[i:i + 60]
    assert s.count('class="sr-only"') >= 3, "each track has a text description"


def test_data_strings_are_escaped_before_html_insertion():
    s = _script()
    # the screen-reader sentences are built as plain text and escaped as a whole where they are inserted
    for var in re.findall(r"var (spoken)=", s):
        assert f"esc({var})" in s and f"+{var}+" not in s, "inserted only through esc()"
        s = re.sub(rf"var {var}=[^;]*;", "", s)
    raw = re.findall(r"'\+\s*([a-z]\w*(?:\.\w+)*\.(?:name|official_name|name_source|basis|code|period|short|r|reason))\s*\+'", s)
    assert not raw, f"inserted without esc(): {raw}"
    assert "function esc(s)" in s and ".replace(/[&<>\"']/g" in s


def test_three_views_with_only_the_first_shown_at_load():
    tabs = re.findall(r'<a href="#([\w-]+)" role="tab"', TEMPLATE)
    assert tabs == ["senator-state", "senate-nation", "committees"]
    assert '<a href="methodology.html">Methodology</a>' in TEMPLATE
    sections = re.findall(r'<section id="([\w-]+)" class="view"[^>]*?( hidden)?>', TEMPLATE)
    assert sections == [("senator-state", ""), ("senate-nation", " hidden"), ("committees", " hidden")]


def test_sources_are_named_with_full_links(pages):
    page, meth = pages["senator-check.html"], pages["methodology.html"]
    assert 'href="https://doi.org/10.7910/DVN/BQKU4M"' in page
    for s in ("Voteview", "American Ideology Project", "Census", "congress-legislators"):
        assert s in page and s in meth, s
    assert "committees-current.json" in meth or "committees-current.json" in page


def test_survey_period_measurement_date_and_observed_dates_are_shown(data):
    assert "'Survey period '+esc(pub.period)" in TEMPLATE and "Survey period '+esc(n.period)" in TEMPLATE
    assert "Measurement date: '+esc(meta.measurement_date)" in TEMPLATE
    assert "Committee membership observed: '+esc(meta.committee_observed)" in TEMPLATE
    assert data["meta"]["measurement_date"] and data["meta"]["committee_observed"]
    assert all(s["senators"][0]["state_public_estimate"]["period"] for s in data["p4"]["states"])


def test_the_two_measurement_systems_are_described_as_separate(pages):
    text = visible_text(pages["senator-check.html"])
    assert "different measurement system" in text and "never on the senator scale" in text
    assert "no distance between" in text


def test_nothing_is_ordered_by_score(data):
    """States and committees are listed by name; senators within a state by the result record's order, never by score."""
    names = [s["name"] for s in data["p4"]["states"]]
    assert names == sorted(names)
    cnames = [c["name"] for c in data["p6"]["committees"]]
    assert cnames == sorted(cnames)
    assert "sort(function(a,b){return a.score.v-b.score.v})" in _script(), "only the three anchor ticks are placed by score"
    assert _script().count(".sort(") == 1


def test_both_colour_themes_are_defined():
    css = (ROOT / "demo" / "civicalign.css").read_text()
    assert "prefers-color-scheme:dark" in css and ':root[data-theme="dark"]' in css
