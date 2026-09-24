"""The supervisor must confirm every published figure from the raw files."""
from pathlib import Path

import pytest

from civicalign.agents.supervisor import checks
from civicalign.config import DEFAULT
from civicalign.pipeline import run

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return run(DEFAULT)


def test_supervisor_confirms_every_figure(report):
    results = checks(report, DEFAULT, ROOT / "demo" / "senator-check.html")
    failed = [c.line() for c in results if not c.ok]
    assert len(results) >= 12
    assert not failed, "\n".join(failed)


def test_supervisor_notices_a_wrong_page_figure(report, tmp_path):
    """Sabotage one number on a copy of the page; the supervisor must catch it."""
    page = (ROOT / "demo" / "senator-check.html").read_text()
    import re
    mblock = re.search(r"const M=\{.*?\};", page, re.S).group(0)
    m = re.search(r'"chM":(-?[0-9.]+)', mblock)
    broken = page.replace(mblock, mblock.replace(m.group(0), f'"chM":{float(m.group(1)) + 0.05:.4f}', 1), 1)
    p = tmp_path / "page.html"
    p.write_text(broken)
    results = checks(report, DEFAULT, p)
    assert any(not c.ok and c.name.startswith("page: Senate middle") for c in results)


def _copy_of_bindings(tmp_path):
    """A Config whose Pillar 1 records are a scratch copy, so they can be sabotaged."""
    import dataclasses
    import shutil
    from civicalign.config import Config
    dst = tmp_path / "119"
    shutil.copytree(DEFAULT.bindings_dir, dst)

    class Scratch(Config):
        @property
        def bindings_dir(self):
            return dst
    return Scratch(**{f.name: getattr(DEFAULT, f.name) for f in dataclasses.fields(DEFAULT)}), dst


def _edit(path, fn):
    import json
    doc = json.loads(path.read_text()); fn(doc); path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


def test_supervisor_catches_a_wrong_next_step(tmp_path):
    from civicalign.agents.supervisor import _binding_checks
    cfg, d = _copy_of_bindings(tmp_path)
    assert _binding_checks(cfg, {}, {})[0].ok
    # S.2 is a Senate bill: it goes to the House, never "back"
    _edit(d / "vote_119_2_00163.json", lambda b: b["receipt"]["next_step"].update(
        actual="Because the Senate changed the text, the amended bill goes back to the House."))
    c = _binding_checks(cfg, {}, {})[0]
    assert not c.ok and "vote_119_2_00163" in c.detail


def test_supervisor_catches_a_failed_vote_described_as_advancing(tmp_path):
    from civicalign.agents.supervisor import _binding_checks
    cfg, d = _copy_of_bindings(tmp_path)
    _edit(d / "vote_119_1_00225.json", lambda b: b["receipt"]["next_step"].update(actual="The joint resolution next goes to the House."))
    c = _binding_checks(cfg, {}, {})[0]
    assert not c.ok and "advancing" in c.detail


def test_supervisor_catches_content_on_a_tracked_reference_and_wrong_metrics(tmp_path):
    from civicalign.agents.supervisor import _context_checks
    cfg, d = _copy_of_bindings(tmp_path)
    assert _context_checks(cfg)[0].ok
    _edit(d / "packets" / "vote_119_1_00095.packet.json", lambda p: p["tracked_references"][0].update(content="<section>…</section>"))
    c = _context_checks(cfg)[0]
    assert not c.ok and "tracked reference" in c.detail
    cfg, d = _copy_of_bindings(tmp_path / "second")
    _edit(d / "packets" / "vote_119_1_00160.packet.json", lambda p: p["metrics"].update(total_source_chars=1))
    c = _context_checks(cfg)[0]
    assert not c.ok and "metrics" in c.detail
