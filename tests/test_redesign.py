"""The redesigned page (2026-09-27): display positions, wording rules, the calm default view,
search and URL state, accessibility and reduced motion -- and that none of it changed a
calculation.

The display position, (nominate_dim1 + 1) x 50, is presentation only. The search and URL
functions live in the page's own script between /* pure:start */ and /* pure:end */ and are
run here with Node when it is installed (it is on the CI runners)."""
import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from civicalign import build_pages as BP
from civicalign.config import DEFAULT
from civicalign.ideology import compute as C
from civicalign.ideology import display as DS
from civicalign.ideology import methodology as M

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "src" / "civicalign" / "templates" / "senator-check.template.html").read_text()
SCRIPT = TEMPLATE[TEMPLATE.index("<script>"):]
SURVEY = {"p4.state_public_estimate", "p4.state_on_senator_scale", "p4.distance", "p5.national_public",
          "p5.chamber_public_gap", "p6.committee_public_drift"}


@pytest.fixture(scope="module")
def data():
    try:
        return BP.payload(DEFAULT)
    except BP.BuildError as e:
        pytest.skip(f"no saved result to build from: {e}")


@pytest.fixture(scope="module")
def page():
    return BP.build(DEFAULT)["senator-check.html"]


def numbers(obj):
    if isinstance(obj, dict):
        if "m" in obj and "s" in obj:
            yield obj
        else:
            for v in obj.values():
                yield from numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from numbers(v)


def static_html(page: str) -> str:
    """The page as served, before its script runs: no embedded data, no script."""
    return re.sub(r"<script\b.*?</script>", " ", page, flags=re.S)


# ---- the display transformation -----------------------------------------------------------------------------

@pytest.mark.parametrize("raw,whole,one", [(-1.0, "0", "0.0"), (-0.5, "25", "25.0"), (0.0, "50", "50.0"), (0.5, "75", "75.0"),
                                           (1.0, "100", "100.0"), (0.587, "79", "79.4"), (0.85, "93", "92.5"),
                                           (-0.546, "23", "22.7"), (0.12008, "56", "56.0"), (0.3195, "66", "66.0"),
                                           (-0.001, "50", "50.0"), (0.009, "50", "50.5"), (0.01, "51", "50.5")])
def test_display_position_is_score_plus_one_times_fifty(raw, whole, one):
    assert DS.position_text(raw, 0) == whole and DS.position_text(raw, 1) == one


def test_half_up_uses_the_exact_decimal_not_binary_float():
    assert DS.position_text(0.85, 0) == "93"          # 92.5 exactly: half-up, not banker's rounding
    assert DS.position_text(-0.03, 0) == "49"         # 48.5 -> 49
    assert DS.points_text(0.03520727378279813) == "1.8" and DS.points_text(-0.0685) == "3.4"


def test_exact_zero():
    assert DS.side_label(0.0) == DS.side_label(-0.0) == "At Voteview’s zero point"
    assert DS.side_label(-0.0001) == "Liberal side of the voting scale" and DS.side_label(0.0001) == "Conservative side of the voting scale"
    assert DS.side_label(None) is None
    assert DS.senate_position_sentence(0.0) == "The Senate sits close to Voteview’s zero point."
    assert DS.population_shift_sentence(0.0) == "Weighting senators by state population does not move it."
    assert DS.shift_detail_sentence(0.0) == "In plain terms, population weighting does not move the Senate average."
    assert DS.shift_words(0.0) is None
    assert DS.committee_sentence(0.0) == "This committee sits close to the Senate midpoint."


@pytest.mark.parametrize("drift,sentence", [
    (0.0399999, "This committee sits close to the Senate midpoint."),
    (-0.0399999, "This committee sits close to the Senate midpoint."),
    (0.04, "This committee sits to the conservative side of the Senate midpoint."),
    (-0.04, "This committee sits to the liberal side of the Senate midpoint."),
    (0.0425, "This committee sits to the conservative side of the Senate midpoint."),
    (0.0345, "This committee sits close to the Senate midpoint."),
    (None, None)])
def test_committee_two_point_rule_boundaries(drift, sentence):
    assert DS.committee_sentence(drift) == sentence


@pytest.mark.parametrize("mean,sentence", [
    (0.0399999, "The Senate sits close to Voteview’s zero point."),
    (-0.0399999, "The Senate sits close to Voteview’s zero point."),
    (0.04, "The Senate sits on the conservative side of the voting scale."),
    (-0.04, "The Senate sits on the liberal side of the voting scale.")])
def test_senate_two_point_rule_boundaries(mean, sentence):
    assert DS.senate_position_sentence(mean) == sentence


@pytest.mark.parametrize("diff,words", [
    (0.0999999, "slightly toward the liberal side"), (0.1, "toward the liberal side"),
    (-0.05, "slightly toward the conservative side"), (-0.1, "toward the conservative side"),
    (0.035207, "slightly toward the liberal side")])
def test_population_shift_rule(diff, words):
    assert DS.shift_words(diff) == words
    assert DS.population_shift_sentence(diff) == f"Weighting senators by state population moves it {words}."
    assert DS.shift_detail_sentence(diff) == f"In plain terms, population weighting moves the Senate average {words} of the voting scale."


def test_words_follow_the_raw_value_not_the_rounded_display():
    # 0.0399 is 1.995 display points: shown as "2.0" points, yet under the 2-point rule, so "close"
    assert DS.points_text(0.0399) == "2.0" and DS.committee_sentence(0.0399) == "This committee sits close to the Senate midpoint."
    # a score that rounds to 50 still takes its side from its sign
    assert DS.position_text(0.004, 0) == "50" and DS.side_label(0.004) == "Conservative side of the voting scale"
    assert DS.position_text(-0.004, 0) == "50" and DS.side_label(-0.004) == "Liberal side of the voting scale"


# ---- the page's data ------------------------------------------------------------------------------------------

def test_every_voteview_position_on_the_page_carries_its_display_position(data):
    n_pos = 0
    for n in numbers(data):
        if n["m"] in BP.POSITIONS and n["v"] is not None:
            assert (n["p0"], n["p1"]) == (DS.position_text(n["v"], 0), DS.position_text(n["v"], 1)), n["p"]
            n_pos += 1
        elif n["m"] in BP.POINTS and n["v"] is not None:
            assert n["pts"] == DS.points_text(n["v"]), n["p"]
        else:
            assert not {"p0", "p1", "pts"} & set(n), n["p"]
    assert n_pos >= 100


def test_no_survey_estimate_is_translated_onto_the_display_scale(data, page):
    for n in numbers(data):
        if n["m"] in SURVEY:
            assert not {"p0", "p1", "pts"} & set(n), n["p"]
    assert not (BP.POSITIONS | BP.POINTS) & SURVEY
    voters = SCRIPT[SCRIPT.index("function votersPanel(st)"):SCRIPT.index("var CURRENT=")]
    assert "scale(" not in voters and ".p0" not in voters and ".p1" not in voters, "the survey estimate is never drawn on the line"


def test_side_labels_and_sentences_come_from_the_rules(data):
    rec = C.load_record(DEFAULT, C.index(DEFAULT)[-1]["input_key"])["results"]
    for st in data["p4"]["states"]:
        for s in st["senators"]:
            assert s["side"] == DS.side_label(s["senator_score"]["v"]), s["id"]
    for c in data["p6"]["committees"]:
        assert c["sentence"] == DS.committee_sentence(rec["pillar6"][c["code"]]["committee_senate_drift"]["value"])
    assert {r["id"] for r in data["display_rules"]} == {DS.POSITION_RULE, DS.SIDE_RULE, DS.SENATE_RULE, DS.SHIFT_RULE, DS.COMMITTEE_RULE}


def test_party_comes_from_the_verified_roster_not_senator_ideology(data):
    roster = {p["id"]["bioguide"]: p["terms"][-1] for p in json.loads(DEFAULT.roster_json.read_text()) if p["terms"][-1]["type"] == "sen"}
    for st in data["p4"]["states"]:
        for s in st["senators"]:
            assert s["party"] == DS.party_abbreviation(roster[s["id"]].get("party")), s["id"]
    src = data["meta"]["identity_source"]
    snap = json.loads((DEFAULT.raw_dir / "SNAPSHOT.json").read_text())
    entry = next(e for e in snap["sources"] if e["file"] == DEFAULT.roster_json.name)
    assert (src["source_version"], src["source_sha256"]) == (str(entry["content_key"]), entry["sha256"])
    rec = (ROOT / "src" / "civicalign" / "ideology" / "records.py").read_text()
    assert '"party"' not in rec.split("senator_ideology", 1)[1].split("constituency_ideology", 1)[0], "party is not a senator_ideology field"


# ---- wording on the page ---------------------------------------------------------------------------------------

def test_no_slash_100_and_no_grade_language(page):
    shown = static_html(page) + SCRIPT
    assert not re.search(r"/\s*100\b", shown), "never /100"
    disclaimer = "A position on a line, not a score, grade, rating, rank or alignment."
    text = (shown + json.dumps(BP.payload(DEFAULT)["display_rules"], ensure_ascii=False)).replace(disclaimer, "")
    for word in ("grade", "rating", "alignment", "effectiveness", "approval", "percentile", "moderate", "centrist",
                 "political center", "political centre", "middle of"):
        assert word not in text.lower(), word


def test_fifty_is_described_only_as_voteviews_zero_point():
    for text in (SCRIPT, (ROOT / "src" / "civicalign" / "ideology" / "display.py").read_text()):
        assert "zero point" in text
        assert not re.search(r"\b50\b[^.]{0,60}\b(middle|moderate|centre|center|neutral)\b", text, re.I)


def test_the_approved_default_sentences():
    assert "'<p class=\"sentence\">Based on how '+esc(s.name)+' has voted in Congress.</p>'" in SCRIPT
    assert "compared with other members of Congress.</p>'+\n      '<p class=\"sentence\">" not in SCRIPT
    default_card = SCRIPT[SCRIPT.index("function senatorCard(s,st)"):SCRIPT.index("function votersPanel(")]
    assert "compared with other members" not in default_card, "that explanation is in See details only"
    assert "Weighting senators by state population moves it" in (ROOT / "src" / "civicalign" / "ideology" / "display.py").read_text()
    assert "See how your senators vote, what the Senate passed, and which bills committees handle." in TEMPLATE
    s = SCRIPT[SCRIPT.index("function details()"):SCRIPT.index("$('whole').innerHTML=")]
    assert "Every state gets two senators regardless of its population. Population weighting gives senators from states with more people more weight." in s


# ---- the calm default view --------------------------------------------------------------------------------------

def test_no_default_state_and_no_senator_cards_before_a_state_is_chosen(page, data):
    assert '<select id="state"><option value="" selected>Choose your state</option></select>' in TEMPLATE
    assert '<option value="" selected>Choose a committee</option>' in TEMPLATE
    html = static_html(page)
    assert "Your two senators will appear here after you choose a state." in html and "Choose your state to begin." in html
    for st in data["p4"]["states"]:
        for s in st["senators"]:
            assert s["name"] not in html, s["name"]
    assert 'class="box sen"' not in html
    load = SCRIPT[SCRIPT.index("var start=parseState("):]
    assert "if(start.state) setState(start.state);" in load and "if(start.committee) setCommittee(start.committee);" in load
    assert len(re.findall(r"(?<![\w.])setState\(", SCRIPT)) == len(re.findall(r"(?<![\w.])setState\(", SCRIPT.replace("if(start.state) setState(start.state);", ""))) + 1
    assert "Alabama" not in TEMPLATE and "'AL'" not in TEMPLATE


def test_default_numbers_are_limited():
    card = SCRIPT[SCRIPT.index("function senatorCard(s,st)"):SCRIPT.index("function votersPanel(")]
    default = card[card.index("var spoken="):]
    assert default.count("num:") == 1 and "rawv(" not in default and "cnt(" not in default, "senator: only the marker's position"
    passed = SCRIPT[SCRIPT.index("$('passed').innerHTML="):SCRIPT.index("// ===== The Senate as a whole")]
    assert passed.count("cnt(") == 2, "what the Senate passed: total passed and total enacted"
    whole = SCRIPT[SCRIPT.index("$('whole').innerHTML="):SCRIPT.index("// ===== Committees")]
    assert "num:" not in whole and "cnt(" not in whole, "the Senate as a whole: no headline number"
    cmte = SCRIPT[SCRIPT.index("function committeeCard(c)"):SCRIPT.index("function setCommittee(")]
    assert cmte.count("cnt(") == 2 and cmte.count("num:") == 0, "committee: the two bill counts; the markers carry no number"
    assert "legend:[['ring','Senate'],['solid','This committee']]" in cmte
    details = SCRIPT[SCRIPT.index("function committeeDetails(c)"):SCRIPT.index("function committeeCard(c)")]
    assert "esc(md.p0)" in details and "esc(sm.p0)" in details, "the exact positions are in See details"


# ---- search and URL state (the page's own functions, run with Node) --------------------------------------------

NODE = shutil.which("node")


def run_pure(body: str):
    if not NODE:
        pytest.skip("node is not installed")
    pure = SCRIPT[SCRIPT.index("/* pure:start"):SCRIPT.index("/* pure:end */")]
    data = BP.payload(DEFAULT)
    small = {"p4": {"states": [{"code": s["code"], "name": s["name"], "senators": [{"name": x["name"], "short": x["short"],
             "party": x["party"], "id": x["id"]} for x in s["senators"]]} for s in data["p4"]["states"]]},
             "p6": {"committees": [{"code": c["code"], "name": c["name"], "official_name": c["official_name"]} for c in data["p6"]["committees"]]}}
    src = pure + f"\nvar D={json.dumps(small)};\n" + body
    out = subprocess.run([NODE, "-e", src], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_search_behaviour():
    r = run_pure("""
      var idx=searchIndex(D); function s(q){return matchSearch(q,idx,8).map(function(x){return [x.kind,x.label]})}
      console.log(JSON.stringify({lujan:s('lujan'), vt:s('VT'), vermont:s('verm'), vet:s('veterans'), none:s('zzzz'),
        empty:s('   '), king:s('king'), fin:s('finance'), many:matchSearch('a',idx,8).length, caps:s('SANDERS')}));""")
    assert r["lujan"] == [["senator", "Ben Luján"]], "accents are ignored"
    assert r["vt"][0] == ["state", "Vermont"] and r["vermont"][0] == ["state", "Vermont"]
    assert ["committee", "Veterans' Affairs"] in r["vet"]
    assert r["none"] == [] and r["empty"] == []
    assert r["king"][0] == ["senator", "Angus King Jr."]
    assert r["fin"] == [["committee", "Finance"]]
    assert r["many"] == 8, "at most eight suggestions"
    assert r["caps"] == [["senator", "Bernie Sanders"]]


def test_search_groups_senators_then_states_then_committees():
    r = run_pure("""var idx=searchIndex(D); console.log(JSON.stringify(matchSearch('new',idx,8).map(function(x){return x.kind})));""")
    order = {"senator": 0, "state": 1, "committee": 2}
    assert [order[k] for k in r] == sorted(order[k] for k in r) and "state" in r


def test_url_state_round_trip():
    r = run_pure("""
      var S=D.p4.states.map(function(s){return s.code}), C=D.p6.committees.map(function(c){return c.code});
      console.log(JSON.stringify({
        full:parseState('?state=vt&committee=ssva','#committees',S,C),
        bad:parseState('?state=ZZ&committee=XX1','#nowhere',S,C),
        old:parseState('','#senate-nation',S,C), old2:parseState('','#senator-state',S,C),
        none:parseState('','',S,C), garbage:parseState('?%E0%A4%A&state=AL','',S,C),
        fmt:formatState({state:'VT',committee:'SSVA',section:'committees'}), fmt0:formatState({state:null,committee:null,section:null}),
        back:parseState(formatState({state:'VT',committee:'SSVA',section:'how'}).split('#')[0],'#how',S,C)}));""")
    assert r["full"] == {"state": "VT", "committee": "SSVA", "section": "committees"}
    assert r["bad"] == {"state": None, "committee": None, "section": None}
    assert r["old"]["section"] == "senate" and r["old2"]["section"] == "senators", "old links still land"
    assert r["none"] == {"state": None, "committee": None, "section": None}, "no default state"
    assert r["garbage"]["state"] == "AL"
    assert r["fmt"] == "?state=VT&committee=SSVA#committees" and r["fmt0"] == ""
    assert r["back"] == {"state": "VT", "committee": "SSVA", "section": "how"}


def test_the_page_writes_its_choices_into_the_url():
    assert "history.replaceState(null,'',location.pathname+formatState({state:CURRENT.state,committee:CURRENT.committee" in SCRIPT
    assert SCRIPT.count("writeURL();") >= 2, "after choosing a state and after choosing a committee"


# ---- accessibility and motion -----------------------------------------------------------------------------------

def test_keyboard_and_screen_reader_support():
    t = TEMPLATE
    assert 'role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="q-list"' in t
    assert 'id="q-list" class="suggest" role="listbox"' in t
    for key in ("'ArrowDown'", "'ArrowUp'", "'Enter'", "'Escape'"):
        assert f"ev.key==={key}" in SCRIPT, key
    assert "aria-activedescendant" in SCRIPT and "aria-selected" in SCRIPT
    # every disclosure is a real button saying whether it is open, and naming what it controls
    assert '<button type="button" class="dbtn" aria-expanded="false" aria-controls="\'+id+\'">' in SCRIPT
    assert t.count('class="dbtn" aria-expanded="false" aria-controls="') >= 3
    assert "<details" not in t and "tabindex=\"0\"" not in t
    assert '<a class="skip" href="#senators">Skip to your senators</a>' in t
    assert 'id="live" class="sr-only" aria-live="polite"' in t
    assert ":focus-visible{outline:3px solid" in t
    for selector in (".topbar nav a{", ".chip{", ".dbtn{", "select,input[type=search]{", ".morebtn{", ".suggest [role=option]{", ".jumpmenu a{"):
        rule = t[t.index(selector):t.index("}", t.index(selector))]
        assert re.search(r"min-height:(4[4-9]|5\d)px", rule), selector
    assert '<nav aria-label="Sections">' in t and t.count("<h1") == 1
    assert all(f'aria-labelledby="h-{s}"' in t for s in ("senators", "passed", "whole", "committees", "how"))


def test_markers_differ_by_shape_and_no_party_colours():
    assert ".mk.ring{background:var(--surface);border:3px solid var(--ink)}" in TEMPLATE
    style = TEMPLATE[:TEMPLATE.index("</style>")]
    assert "--rep" not in style and "--dem" not in style, "no red or blue by party"
    assert "gradient" not in style


def test_reduced_motion():
    assert "@media (prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important;animation:none!important" in TEMPLATE
    assert "@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}" in TEMPLATE
    assert "var REDUCED=!!(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches);" in SCRIPT
    assert "behavior:REDUCED?'auto':'smooth'" in SCRIPT and "if(REDUCED){p.hidden=!open" in SCRIPT
    assert "style=\"--x:'+(REDUCED?x:50)+'%\"" in SCRIPT, "markers start in place when motion is reduced"


def test_no_network_or_model_in_the_page():
    for bad in ("fetch(", "XMLHttpRequest", "localStorage", "sessionStorage", "openai", "anthropic"):
        assert bad not in SCRIPT, bad


# ---- nothing underneath changed -------------------------------------------------------------------------------

def test_presentation_is_never_a_calculation_input():
    for mod in ("pillars.py", "compute.py", "bills.py", "bill_outcomes.py", "bill_tallies.py", "ingest.py", "methodology.py"):
        tree = ast.parse((ROOT / "src" / "civicalign" / "ideology" / mod).read_text())
        names = [a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names]
        assert "display" not in names and not any(getattr(n, "module", "") and "display" in n.module
                                                    for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)), mod
    assert C.plan(DEFAULT)["mode"] == "unchanged" and C.verify(DEFAULT) == []


def test_all_calculated_values_are_the_saved_record(data):
    rec = C.load_record(DEFAULT, C.index(DEFAULT)[-1]["input_key"])
    for n in numbers(data):
        if n["p"].startswith(("pillar4.", "pillar5.", "pillar6.")):
            node = rec["results"]
            for part in n["p"].split("."):
                node = node[int(part)] if isinstance(node, list) else node[part]
            assert n["v"] == (node if isinstance(node, int) else node["value"]), n["p"]


def test_methodology_page_documents_every_display_rule(data):
    meth = BP.build(DEFAULT)["methodology.html"]
    for r in data["display_rules"]:
        assert f'id="{r["id"]}"' in meth and r["rule"].split(",")[0][:30].replace("&", "&amp;") in meth
    assert set(data["methods"]) == set(M.REGISTRY), "every existing methodology entry is still published"


def test_one_neutral_accent_and_no_party_or_judgment_colours():
    style = TEMPLATE[:TEMPLATE.index("</style>")]
    accents = set(re.findall(r"--accent:(#[0-9A-Fa-f]{6})", style))
    assert len(accents) == 2, "one accent, with its dark-theme variant"
    for hexcol in accents:
        r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
        assert r > b and r >= g, f"{hexcol}: a warm neutral, not a blue"
        assert not (r > 150 and g < 80 and b < 80), f"{hexcol}: not a red"
        assert not (g > r and g > b), f"{hexcol}: not a green"
    assert ".mk{" in style and "background:var(--accent)" in style[style.index(".mk{"):style.index("}", style.index(".mk{"))]
    assert ".mk.ring{background:var(--surface);border:3px solid var(--ink)}" in style


def test_jump_menu_is_keyboard_and_screen_reader_friendly():
    assert '<button type="button" class="chip" id="jump" aria-expanded="false" aria-controls="jump-menu">Jump to' in TEMPLATE
    assert '<ul class="jumpmenu" id="jump-menu" hidden>' in TEMPLATE
    assert "jump.setAttribute('aria-expanded',open?'true':'false'); menu.hidden=!open" in SCRIPT
    assert "if(ev.key==='Escape'&&!menu.hidden){jumpOpen(false); jump.focus()}" in SCRIPT
    assert "document.querySelectorAll('.topbar nav a, #jump-menu a')" in SCRIPT, "the active section is marked in both"


def test_each_answer_has_a_quiet_source_line_without_technical_detail():
    lines = re.findall(r"trust\('([^']+)'\)", SCRIPT)
    assert lines == ["Voteview voting records", "Official GovInfo bill records", "Voteview + Census data",
                     "Committee rosters, GovInfo bill records + Voteview"]
    assert "function trust(sources){return '<p class=\"trust\">'+esc(sources)+' · <span class=\"nw\">Checked before publishing</span></p>'}" in SCRIPT
    for text in lines:
        assert not re.search(r"[0-9a-f]{8,}|_v\d|\.jsonl|senator_ideology|bill_sponsor|fingerprint|sha", text, re.I), text
    style = TEMPLATE[:TEMPLATE.index("</style>")]
    rule = style[style.index(".trust{"):style.index("}", style.index(".trust{"))]
    assert "color:var(--muted)" in rule and "font-size:12.5px" in rule, "small, neutral secondary text"
    for fn, text in (("function senatorCard(s,st)", "Voteview voting records"), ("$('passed').innerHTML=", "Official GovInfo bill records"),
                     ("$('whole').innerHTML=", "Voteview + Census data"), ("function committeeCard(c)", "Committee rosters")):
        start = SCRIPT.index(fn)
        assert text in SCRIPT[start:start + 2500], fn


def test_how_civicalign_works_explains_the_pipeline_plainly():
    assert "<p>CivicAlign collects public government data, checks it independently, and turns it into plain-language explanations.</p>" in TEMPLATE
    for text in ("<strong>Where the data comes from:</strong>", "<strong>Updated daily:</strong>",
                 "<strong>Checked before publishing:</strong> a separate checker recounts every published number",
                 "<strong>No AI:</strong> no AI is used to classify the political data."):
        assert text in TEMPLATE, text
