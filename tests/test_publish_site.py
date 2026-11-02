"""The published folder: the integrated site is the default, old links reach it, and the
verified old page is kept unchanged for rollback."""
import re
from pathlib import Path

import pytest

from civicalign import publish_site as P

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "update.yml").read_text()


@pytest.fixture
def demo(tmp_path):
    d = tmp_path / "demo"
    (d / "data").mkdir(parents=True)
    (d / "civicalign.html").write_text("new site")
    (d / "senator-check.html").write_bytes(b"old page \xc2\xb7 bytes\n")
    (d / "index.html").write_text('<meta http-equiv="refresh" content="0; url=civicalign.html">')
    (d / "data" / "votes.json").write_text("[]")
    return d


def test_the_old_address_redirects_and_the_original_is_kept(demo, tmp_path):
    out = tmp_path / "site"
    P.arrange(demo, out)
    assert (out / P.BACKUP).read_bytes() == b"old page \xc2\xb7 bytes\n"
    page = (out / P.OLD).read_text()
    assert page == P.REDIRECT and 'location.replace("civicalign.html"' in page and "url=civicalign.html" in page
    assert (out / "civicalign.html").read_text() == "new site" and (out / "data" / "votes.json").exists()


def test_the_verified_folder_is_not_changed(demo, tmp_path):
    P.arrange(demo, tmp_path / "site")
    assert (demo / P.OLD).read_bytes() == b"old page \xc2\xb7 bytes\n" and not (demo / P.BACKUP).exists()


def test_an_earlier_publish_folder_is_replaced(demo, tmp_path):
    out = tmp_path / "site"
    out.mkdir()
    (out / "stale.html").write_text("old")
    P.arrange(demo, out)
    assert not (out / "stale.html").exists()


@pytest.mark.parametrize("name", [P.SITE, P.OLD, "index.html"])
def test_a_missing_page_stops_the_job(demo, tmp_path, name):
    (demo / name).unlink()
    with pytest.raises(SystemExit):
        P.arrange(demo, tmp_path / "site")


def test_a_home_page_that_opens_something_else_stops_the_job(demo, tmp_path):
    (demo / "index.html").write_text('<meta http-equiv="refresh" content="0; url=senator-check.html">')
    with pytest.raises(SystemExit):
        P.arrange(demo, tmp_path / "site")


def test_old_section_links_reach_real_sections():
    site = (ROOT / "src" / "civicalign" / "templates" / "site.template.html").read_text()
    old = (ROOT / "src" / "civicalign" / "templates" / "senator-check.template.html").read_text()
    targets = re.findall(r'(\w+):"(#/\w+)"', P.REDIRECT)
    assert len(targets) == 4
    for section, target in targets:
        assert f'href="#{section}"' in old, section
        assert f'data-nav="{target[2:]}"' in site, target


def test_only_the_arranged_folder_is_uploaded_after_every_gate():
    upload = WORKFLOW[WORKFLOW.index("Upload the verified site"):WORKFLOW.index("  publish:")]
    assert "path: _site" in upload and "path: demo" not in WORKFLOW
    assert WORKFLOW.index("civicalign.agents.supervisor") < WORKFLOW.index("civicalign.publish_site") < WORKFLOW.index("upload-pages-artifact")
