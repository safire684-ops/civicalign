"""Senators filters and sorting, committee ordering, profile wording, and the bill pages.

The list logic lives in the page's script between `lists:start` and `lists:end`; these tests run that
exact code in Node against the real site data, so what's tested is what ships. Bill details come from
the official bill-status records, and the independent checker must catch any change to them.
"""
import copy
import json
import re
import shutil
import subprocess

import pytest

from civicalign import build_site as BS
from civicalign import legislative as L
from civicalign.agents import supervisor as S
from civicalign.config import DEFAULT

from test_site import TEMPLATE, failed

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node is needed to run the page's own list code")
SCRIPT = TEMPLATE[TEMPLATE.rindex("<script>") + 8:TEMPLATE.rindex("</script>")]
LISTS = SCRIPT[SCRIPT.index("/* lists:start"):SCRIPT.index("/* lists:end */")]


@pytest.fixture(scope="module")
def core():
    return BS.assemble(DEFAULT)[0]


@pytest.fixture(scope="module")
def details():
    return BS.bill_details(DEFAULT, L.load(DEFAULT)["bills"])


def js(code: str, data) -> object:
    """Runs the page's list functions plus `code` (which must print JSON) with `data` as DATA."""
    src = LISTS + f"\nconst DATA={json.dumps(data)};\n" + code
    done = subprocess.run([NODE, "-e", src], text=True, capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def senators(core, f):
    return js(f"console.log(JSON.stringify(senatorList(DATA,{json.dumps(f)}).map(s=>s.id)))", core["senators"])


def seated(core):
    return [s for s in core["senators"] if s["seated"]]


# ---- regions ----
def test_every_state_has_a_census_region(core):
    assert set(BS.REGION.values()) == {"Northeast", "Midwest", "South", "West"}
    assert len(BS.REGION) == 51                                    # 50 states and DC
    assert {k: sum(1 for r in BS.REGION.values() if r == k) for k in BS.REGIONS} == {"Northeast": 9, "Midwest": 12, "South": 17, "West": 13}
    assert all(s["region"] == BS.REGION[s["state"]] for s in core["senators"])


# ---- senators: sorting ----
@needs_node
def test_default_order_is_state_then_last_name(core):
    want = [s["id"] for s in sorted(seated(core), key=lambda s: (s["state_name"], s["last"], s["name"]))]
    assert senators(core, {}) == want
    assert senators(core, {"sort": "state"}) == want


@needs_node
def test_sort_by_last_name(core):
    got = [next(s for s in core["senators"] if s["id"] == i) for i in senators(core, {"sort": "name"})]
    assert [s["last"] for s in got] == sorted(s["last"] for s in seated(core))


@needs_node
def test_sort_by_party_keeps_parties_together(core):
    got = [next(s for s in core["senators"] if s["id"] == i)["party"] for i in senators(core, {"sort": "party"})]
    assert got == sorted(got, key={"D": 0, "I": 1, "R": 2}.get)


@needs_node
@pytest.mark.parametrize("sort,sign", [("liberal", 1), ("conservative", -1)])
def test_sort_by_position_uses_voteview_scores(core, sort, sign):
    by = {s["id"]: s for s in core["senators"]}
    got = [by[i] for i in senators(core, {"sort": sort})]
    known = [s["position"]["v"] for s in got if s["position"]]
    assert known == sorted(known, key=lambda v: sign * v)
    assert all(s["position"] for s in got[:len(known)]), "senators with no position go last"


# ---- senators: filters, alone and combined ----
@needs_node
@pytest.mark.parametrize("party", ["D", "R", "I"])
def test_party_filter(core, party):
    assert set(senators(core, {"party": party})) == {s["id"] for s in seated(core) if s["party"] == party}


@needs_node
def test_region_state_and_committee_filters(core):
    assert set(senators(core, {"region": "West"})) == {s["id"] for s in seated(core) if s["region"] == "West"}
    assert set(senators(core, {"state": "MA"})) == {s["id"] for s in seated(core) if s["state"] == "MA"}
    finance = {m["id"] for m in next(c for c in core["committees"] if c["code"] == "SSFI")["members"]}
    assert set(senators(core, {"committee": "SSFI"})) == finance & {s["id"] for s in seated(core)}


@needs_node
def test_filters_combine(core):
    finance = {m["id"] for m in next(c for c in core["committees"] if c["code"] == "SSFI")["members"]}
    want = {s["id"] for s in seated(core) if s["party"] == "D" and s["region"] == "West" and s["id"] in finance}
    assert set(senators(core, {"party": "D", "region": "West", "committee": "SSFI"})) == want and want
    assert senators(core, {"region": "West", "state": "MA"}) == []


@needs_node
def test_position_filters_follow_the_scale(core):
    by = {s["id"]: s for s in core["senators"]}
    assert all(by[i]["position"]["v"] < 0 for i in senators(core, {"position": "liberal"}))
    assert all(by[i]["position"]["v"] > 0 for i in senators(core, {"position": "conservative"}))
    bands = [senators(core, {"position": f"{lo}-{lo + 20}"}) for lo in range(0, 100, 20)]
    for lo, ids in zip(range(0, 100, 20), bands):
        assert all(lo <= (by[i]["position"]["v"] + 1) * 50 <= lo + 20 for i in ids)
    scored = {s["id"] for s in seated(core) if s["position"]}
    flat = [i for ids in bands for i in ids]
    assert sorted(flat) == sorted(scored), "every scored senator falls in exactly one band"


def test_reset_and_shareable_links():
    assert '$("#sreset").onclick=()=>go("#/senators")' in TEMPLATE
    assert 'history.replaceState(null,"",withQuery("#/senators"' in TEMPLATE
    assert 'const SFILTERS=["party","position","region","state","committee","sort"]' in TEMPLATE


@needs_node
def test_routes_ignore_the_query_string():
    fns = "".join(re.search(p, SCRIPT).group(0) for p in (r"const query=.*?;\n", r"const withQuery=.*?;\n", r"function route\(\)\{.*?\}\n"))
    code = fns + """const out=[];for(const h of ["#/senators?party=D","#/bills/hr1?tab=votes&senator=W000817","#/committees/SSFI"]){
      globalThis.location={hash:h};out.push([route(),query()])}
    out.push(withQuery("#/senators",{party:"D",sort:""}));console.log(JSON.stringify(out))"""
    done = subprocess.run([NODE, "-e", code], text=True, capture_output=True, timeout=60) if NODE else None
    if done is None:
        pytest.skip("Node is needed")
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == [[["senators"], {"party": "D"}], [["bills", "hr1"], {"tab": "votes", "senator": "W000817"}],
                                       [["committees", "SSFI"], {}], "#/senators?party=D"]


# ---- committees ----
@needs_node
def test_committees_sort_by_midpoint_with_unavailable_last(core):
    coms = core["committees"]
    order = lambda sort: js(f"console.log(JSON.stringify(committeeList(DATA,{json.dumps(sort)}).map(c=>c.code)))", coms)
    by = {c["code"]: c for c in coms}
    mid = lambda c: c["committee_median"]["v"] if c.get("committee_median") and c["committee_median"]["s"] == "AVAILABLE" else None
    lib = [by[c] for c in order("liberal")]
    known = [mid(c) for c in lib if mid(c) is not None]
    assert known == sorted(known) and len(known) >= 15
    assert all(mid(c) is None for c in lib[len(known):])
    con = [mid(by[c]) for c in order("conservative") if mid(by[c]) is not None]
    assert con == sorted(con, reverse=True)
    assert [by[c]["name"] for c in order("name")] == sorted(c["name"] for c in coms)


def test_committee_markers_are_explained_as_positions():
    assert "These are positions, not grades or percentages." in TEMPLATE
    assert '[["name","A to Z"],["liberal","Liberal to conservative"],["conservative","Conservative to liberal"]]' in TEMPLATE
    assert "Midpoint: ${NA}" in TEMPLATE, "a committee with no midpoint says so"


def test_committee_members_open_their_profile_and_can_be_cleared():
    assert 'href="#/senators/${m.id}?from=${c.code}"' in TEMPLATE
    assert '× Clear selection</a>' in TEMPLATE and '← All committees' in TEMPLATE
    assert '← Back to ${esc(from.name)}' in TEMPLATE


# ---- the profile ----
def test_the_profile_has_no_state_comparison_card():
    assert "State vs Senator" not in TEMPLATE
    body = TEMPLATE[TEMPLATE.index("async function vSenator("):TEMPLATE.index("function allVotes(")]
    assert "s.public" not in body and "state_public_estimate" not in body


def test_the_voting_position_is_explained_not_scored():
    body = TEMPLATE[TEMPLATE.index("async function vSenator("):TEMPLATE.index("function allVotes(")]
    assert "<h3>Voting position</h3>" in body and "line(s.position.p1,[med.p1])" in body and "${scaleEnds}" in body
    assert "It isn't a grade, a percentage or a measure of agreement" in body
    assert "%" not in body.replace("${", "").split("<small>Position</small>")[0].split("Voting position")[1][:400]
    assert 'id="howto"' in body and "${howToRead()}" in body and "#/about/read" in body


def test_how_to_read_is_on_the_about_page_too():
    assert '<div class="card" id="read">' in TEMPLATE and TEMPLATE.count("${howToRead()}") == 2


def test_recent_votes_open_the_bill_explanation():
    assert "${v.bill?await billBrief(v.bill,X,sid):\"\"}" in TEMPLATE
    brief = TEMPLATE[TEMPLATE.index("async function billBrief("):TEMPLATE.index("async function voteBody(")]
    assert "summarySource(d.summary)" in brief and "Provisional facts" in brief and "Explanation coming soon" in brief
    assert "Official summary: ${NA}." in brief


def test_finances_stay_unavailable_and_say_why():
    assert re.search(r"Estimated Net Worth</b><span>\$\{NA\}", TEMPLATE) and re.search(r"Stocks Held</b><span>\$\{NA\}", TEMPLATE)
    assert 'id="finances"' in TEMPLATE and "value range" in TEMPLATE and "doesn't prove someone still owns a stock" in TEMPLATE


def test_last_updated_is_on_every_page():
    assert 'const updated=()=>`<b>Last updated ${fmtDate(D.dates.snapshot)}.</b>`' in TEMPLATE
    assert '<p class="datanote">${updated()}' in TEMPLATE and '$("#ft").innerHTML=`${updated()}' in TEMPLATE


# ---- bills ----
def test_every_bill_page_has_four_sections():
    assert 'const BTABS=[["overview","Overview"],["votes","Voting Record"],["explain","Explanation"],["sources","Sources"]]' in TEMPLATE
    assert 'role="tablist"' in TEMPLATE and 'role="tab"' in TEMPLATE and 'role="tabpanel"' in TEMPLATE
    assert "if(X.bById[id])return vBill(x,X,h)" in TEMPLATE


def test_the_overview_has_every_required_part():
    body = TEMPLATE[TEMPLATE.index("function billOverview("):TEMPLATE.index("function billExplain(")]
    for part in ("<h4>Sponsor</h4>", "<h4>Summary</h4>", "<h4>What it would change</h4>", "<h4>What a Yes or No vote meant</h4>",
                 "<h4>Current status</h4>", "<h4>How a senator voted</h4>"):
        assert part in body, part
    assert "CivicAlign doesn't write its own" in body and "${NA}" in body


def test_bills_link_with_the_senator_from_every_entry_point():
    assert "withQuery(`#/bills/${rec.id}`,{senator:s.id})" in TEMPLATE        # issue positions
    assert "withQuery(`#/bills/${id}`,{senator:sid})" in TEMPLATE             # a vote's bill brief
    assert '<a href="#/bills/${k}">S. ${b.n}</a>' in TEMPLATE                 # committee bill lists
    assert 'href="#/bills/${esc(bill.id)}">Open ${esc(bill.label)}</a>' in TEMPLATE   # committee votes


def test_bill_details_cover_every_bill(details):
    drop = L.load(DEFAULT)
    assert set(details) == {b["id"] for b in drop["bills"]}
    have = [d for d in details.values() if d]
    assert len(have) == len(details), "every measure type's archive is in the snapshot"
    assert all(d["sponsor"]["party_name"] in ("Democrat", "Republican", "Independent") for d in have if d["sponsor"])
    assert sum(1 for d in have if d["summary"]) >= 100
    for d in have:
        for p in (d["summary"] or {"paragraphs": []})["paragraphs"]:
            assert p and "<" not in p and "&nbsp;" not in p and p == p.strip()
        assert d["source"].startswith("https://www.govinfo.gov/bulkdata/BILLSTATUS/119/")


def test_a_senate_sponsor_links_to_their_profile(core, details):
    ids = {s["id"] for s in core["senators"]}
    senate = [d["sponsor"] for d in details.values() if d and d["sponsor"] and d["sponsor"]["id"] in ids]
    assert senate and "SEN[p.id]?`<a href=\"#/senators/${esc(p.id)}\">" in TEMPLATE
    party = {s["id"]: s["party_name"] for s in core["senators"]}
    assert all(sp["party_name"] == party[sp["id"]] for sp in senate if sp["id"] in party), "sponsor parties agree with the roster"


BILL = """<billStatus><bill><number>9</number><type>S</type><title>A bill to do a thing.</title>
<titles><item><titleType>Short Titles as Introduced</titleType><title>Thing Act</title></item></titles>
<relatedBills><item><latestAction><actionDate>2025-01-01</actionDate><text>Related bill action</text></latestAction></item></relatedBills>
<sponsors><item><bioguideId>X000001</bioguideId><fullName>Sen. Doe, Jan [I-ME]</fullName><firstName>Jan</firstName><lastName>Doe</lastName><party>I</party><state>ME</state></item></sponsors>
<summaries><summary><versionCode>00</versionCode><actionDate>2025-02-01</actionDate><actionDesc>Introduced in Senate</actionDesc><updateDate>2025-02-03</updateDate>
<cdata><text>&lt;p&gt;&lt;strong&gt;Thing Act&lt;/strong&gt;&lt;/p&gt;&lt;p&gt;This bill does&amp;nbsp;a thing.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;One&lt;/li&gt;&lt;li&gt;Two&lt;/li&gt;&lt;/ul&gt;</text></cdata></summary>
<summary><versionCode>01</versionCode><actionDate>2024-12-01</actionDate><actionDesc>Older</actionDesc><updateDate>2024-12-02</updateDate><text><![CDATA[<p>Old.</p>]]></text></summary></summaries>
<latestAction><actionDate>2025-03-01</actionDate><text>Read twice.</text></latestAction></bill></billStatus>"""


def test_a_bill_record_is_read_as_published():
    r = BS.bill_record(BILL.encode())
    assert r["sponsor"] == {"id": "X000001", "name": "Jan Doe", "full": "Sen. Doe, Jan [I-ME]", "party": "I", "party_name": "Independent", "state": "ME"}
    assert r["summary"]["paragraphs"] == ["Thing Act", "This bill does a thing.", "One", "Two"]
    assert r["summary"]["action"] == "Introduced in Senate" and r["summary"]["date"] == "2025-02-01", "the latest summary is used"
    assert r["latest_action"] == {"date": "2025-03-01", "text": "Read twice."}, "a related bill's action is never the bill's own"
    assert r["short_title"] == "Thing Act"


# ---- the independent check ----
def test_the_checker_confirms_and_catches_changed_bill_details(details):
    drop = L.load(DEFAULT)
    assert not failed(S.site_bill_detail_checks(DEFAULT, drop, details), "Site: bill sponsors")
    one = next(k for k, d in details.items() if d and d["sponsor"] and d["summary"] and d["latest_action"])
    for change in (lambda d: d["sponsor"].update(party="R" if d["sponsor"]["party"] != "R" else "D"),
                   lambda d: d["sponsor"].update(party_name="Independent" if d["sponsor"]["party_name"] != "Independent" else "Democrat"),
                   lambda d: d["summary"]["paragraphs"].append("An invented sentence."),
                   lambda d: d["latest_action"].update(text="Became law."),
                   lambda d: d.update(short_title="Made-Up Act"),
                   lambda d: d.update(summary=None)):
        bad = copy.deepcopy(details)
        change(bad[one])
        assert failed(S.site_bill_detail_checks(DEFAULT, drop, bad), "Site: bill sponsors"), change
    bad = copy.deepcopy(details)
    bad["s999999"] = bad[one]
    assert failed(S.site_bill_detail_checks(DEFAULT, drop, bad), "Site: bill sponsors")


def test_the_page_never_writes_its_own_summary():
    assert "Official summary by the Congressional Research Service (Library of Congress)" in TEMPLATE
    body = TEMPLATE[TEMPLATE.index("function summaryParas("):TEMPLATE.index("async function billBrief(")]
    assert "s.paragraphs" in body and "esc(t)" in body


def test_data_health_tracks_bill_records_summaries_and_explanations():
    from civicalign import health as H
    items = {i["code"]: i for i in H.report(DEFAULT)["items"]}
    assert items["bill_records"]["level"] == "ok" and "official bill-status record" in items["bill_records"]["text"]
    assert "Congressional Research Service" in items["bill_summaries"]["text"]
    assert items["bill_explanations"]["level"] == "warn" and "Explanation coming soon" in items["bill_explanations"]["text"]
