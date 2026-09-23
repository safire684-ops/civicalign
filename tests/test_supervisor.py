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
