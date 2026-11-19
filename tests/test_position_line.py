"""The voting-position line drawn on profiles, comparisons, committees and the Senate view.

Regression for two production bugs (2026-11-19):
  * no fixed 50 mark, so a senator between 50 and the Senate median (Lisa Murkowski, 60.2, median 66.0) sat left of
    the only tick and read as liberal;
  * the position number sat in a separate column instead of with its marker.
The tests run the page's own posLine code in Node (between posline:start and posline:end).
"""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from civicalign import build_site as BS
from civicalign.config import DEFAULT

from test_site import TEMPLATE

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node is needed to run the page's own line code")
SCRIPT = TEMPLATE[TEMPLATE.rindex("<script>") + 8:TEMPLATE.rindex("</script>")]
BLOCK = SCRIPT[SCRIPT.index("/* posline:start"):SCRIPT.index("/* posline:end */")]
ESC = re.search(r"const esc=.*?;\n", SCRIPT).group(0)


def render(calls: list) -> list[str]:
    """posLine(...) for each [p, opts] pair, as HTML strings."""
    src = ESC + BLOCK + f"\nconsole.log(JSON.stringify({json.dumps(calls)}.map(([p,o])=>posLine(p,o))))"
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "line.js"
        f.write_text(src)
        done = subprocess.run([NODE, str(f)], text=True, capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def left(html: str, cls: str) -> list[float]:
    return [float(x) for x in re.findall(rf'<span class="{cls}"[^>]*style="left:([\d.]+)%"', html)]


@pytest.fixture(scope="module")
def core():
    return BS.assemble(DEFAULT)[0]


@needs_node
def test_lisa_murkowski_is_drawn_on_the_conservative_side_with_both_references(core):
    s = next(x for x in core["senators"] if x["id"] == "M001153")
    med = core["senate"]["median"]["p1"]
    assert s["position"]["v"] > 0 and s["side"].startswith("Conservative"), "her verified Voteview score is right of zero"
    html, = render([[s["position"]["p1"], {"refs": [{"kind": "senate", "v": med}]}]])
    k, z, t = left(html, "k")[0], left(html, "z")[0], left(html, "t senate")[0]
    assert z == 50 and k == float(s["position"]["p1"]) and k > z, "marker right of the fixed 50 line"
    assert t == float(med) and t != z, "the Senate median is its own tick, not the 50 line"
    assert "50: Voteview's zero point" in html and f"Senate median: {med}" in html


@needs_node
@pytest.mark.parametrize("p,side", [("12.8", "below"), ("50.0", "at"), ("60.2", "above"), ("96.8", "above")])
def test_every_position_is_plotted_at_its_own_value_with_50_fixed(p, side):
    html, = render([[p, {"refs": [{"kind": "senate", "v": "66.0"}]}]])
    k, z = left(html, "k")[0], left(html, "z")[0]
    assert z == 50 and k == float(p)
    assert {"below": k < 50, "at": k == 50, "above": k > 50}[side]


@needs_node
def test_the_number_sits_above_its_marker_once_and_stays_inside_the_ends():
    out = render([["60.2", {}], ["2.5", {}], ["97.4", {}], ["0", {}], ["100", {}]])
    for html, p in zip(out, ["60.2", "2.5", "97.4", "0", "100"]):
        nums = re.findall(r'<span class="pl-n ?([lr]?)" style="left:([\d.]+)%">([^<]+)</span>', html)
        assert len(nums) == 1, "exactly one position number per line"
        align, at, text = nums[0]
        assert text == p and float(at) == left(html, "k")[0], "the number is placed at its marker"
        assert html.index("pl-n") < html.index('class="line'), "the number comes before (above) the line"
        assert align == ("l" if float(p) < 6 else "r" if float(p) > 94 else "")


@needs_node
def test_no_position_draws_no_marker_and_no_number():
    html, = render([[None, {"refs": [{"kind": "senate", "v": "66.0"}]}]])
    assert 'class="line off"' in html and not left(html, "k") and "pl-n" not in html and "not available" in html


@needs_node
def test_committee_and_weighted_references_are_distinct():
    html, = render([["41.2", {"refs": [{"kind": "committee", "v": "45.0"}, {"kind": "weighted", "v": "63.0"}]}]])
    assert left(html, "t committee") == [45.0] and left(html, "t weighted") == [63.0] and left(html, "z") == [50.0]
    assert "Committee median: 45.0" in html and "Population-weighted average: 63.0" in html


def test_every_position_line_uses_the_shared_component():
    assert not re.search(r"(?<![A-Za-z.])line\(", SCRIPT), "the old helper had no 50 mark; nothing may call it"
    assert SCRIPT.count("posLine(") >= 8                       # definition + 7 call sites
    for where in ("vSenator", "vCommittees", "vSenate", "vCompare"):
        start = SCRIPT.index(f"function {where}(") if f"function {where}(" in SCRIPT else SCRIPT.index(f"async function {where}(")
        assert "posLine(" in SCRIPT[start:start + 12000], where
    assert '<span class="z" style="left:50%"></span>' in SCRIPT, "committee markers carry the 50 mark too"


def test_the_profile_shows_the_number_only_on_the_line():
    body = SCRIPT[SCRIPT.index("async function vSenator("):SCRIPT.index("function allVotes(")]
    summary = body[body.index("<h3>Voting position</h3>") - 200:body.index("</summary>", body.index("<h3>Voting position</h3>"))]
    assert 'summary class="pos"' in summary and "big-n" not in summary and "position.p0" not in summary
    assert "posLine(s.position&&s.position.p1,{refs:[{kind:\"senate\",v:med.p1}]})" in summary


def test_the_line_layout_has_room_for_the_number_and_works_on_phones():
    assert ".pl{position:relative;padding-top:20px" in TEMPLATE and ".pl-n{position:absolute;top:0;transform:translateX(-50%)" in TEMPLATE
    assert ".prow>summary.pos{grid-template-columns:36px minmax(0,1fr) 12px}" in TEMPLATE      # phone rule
    assert ".line .z{position:absolute" in TEMPLATE and "border-left:2px dashed" in TEMPLATE
