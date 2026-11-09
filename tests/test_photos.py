"""Senator photos: saved once from official sources, checked, published byte for byte, and never faked. No network."""
import copy
import hashlib
import json
import re
import struct
from dataclasses import replace

import pytest

from civicalign import build_site as BS
from civicalign import photos as PH
from civicalign.agents import supervisor as S
from civicalign.config import DEFAULT

from test_site import TEMPLATE, failed


def jpeg(w=225, h=275, pad=4000) -> bytes:
    """A minimal JPEG header with a frame of w x h, padded to a realistic size."""
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + sof + b"\x00" * pad + b"\xff\xd9"


@pytest.fixture
def cfg(tmp_path):
    return replace(DEFAULT, ideology_dir=tmp_path / "data" / "ideology")


def source(answers):
    """A fake fetch: url -> bytes, None (no such file) or an exception to raise."""
    calls = []
    def get(url):
        calls.append(url)
        a = answers.get(url.split("/")[2], None)
        if isinstance(a, Exception):
            raise a
        return a(url) if callable(a) else a
    get.calls = calls
    return get


US, BIO = "unitedstates.github.io", "bioguide.congress.gov"


def test_jpeg_size_and_problems():
    assert PH.jpeg_size(jpeg(225, 275)) == (225, 275)
    assert PH.problem(jpeg()) is None
    assert PH.problem(b"<html>Not found</html>" * 400) == "not a JPEG"
    assert PH.problem(jpeg(pad=10)) == "too small to be a photo"
    assert PH.problem(jpeg(400, 200)).startswith("not portrait-shaped")
    assert PH.problem(None) == "no file"


def test_a_photo_is_saved_with_its_source(cfg):
    get = source({US: jpeg()})
    r = PH.update(cfg, {"X000001": "Jan Doe"}, get=get)
    m = PH.read_manifest(cfg)
    assert r["saved"] == ["X000001"] and not r["unavailable"]
    p = m["photos"]["X000001"]
    assert p["url"] == "https://unitedstates.github.io/images/congress/225x275/X000001.jpg" and p["source"].startswith("unitedstates/images")
    assert p["sha256"] == hashlib.sha256((PH.home(cfg) / "X000001.jpg").read_bytes()).hexdigest() and (p["width"], p["height"]) == (225, 275)
    assert PH.verify(cfg) == []


def test_the_second_source_is_used_when_the_first_has_none(cfg):
    PH.update(cfg, {"X000001": "Jan Doe"}, get=source({US: None, BIO: jpeg(180, 225)}))
    assert PH.read_manifest(cfg)["photos"]["X000001"]["url"] == "https://bioguide.congress.gov/bioguide/photo/X/X000001.jpg"


def test_an_error_page_is_never_saved_as_a_photo(cfg):
    PH.update(cfg, {"X000001": "Jan Doe"}, get=source({US: b"<html>error</html>" * 500, BIO: None}))
    m = PH.read_manifest(cfg)
    assert "X000001" not in m["photos"] and not (PH.home(cfg) / "X000001.jpg").exists()
    assert [t["result"] for t in m["unavailable"]["X000001"]["tried"]] == ["not a JPEG", "no file"]


def test_a_missing_photo_is_listed_and_asked_for_again(cfg):
    PH.update(cfg, {"X000001": "Jan Doe"}, get=source({}))
    since = PH.read_manifest(cfg)["unavailable"]["X000001"]["since"]
    get = source({US: jpeg()})
    PH.update(cfg, {"X000001": "Jan Doe"}, get=get)
    m = PH.read_manifest(cfg)
    assert get.calls and "X000001" in m["photos"] and "X000001" not in m["unavailable"] and since


def test_saved_photos_are_not_downloaded_again(cfg):
    PH.update(cfg, {"X000001": "Jan Doe"}, get=source({US: jpeg()}))
    get = source({US: AssertionError("must not be called")})
    PH.update(cfg, {"X000001": "Jan Doe"}, get=get)
    assert get.calls == []


def test_a_network_failure_keeps_what_was_saved(cfg):
    PH.update(cfg, {"X000001": "Jan Doe"}, get=source({US: jpeg()}))
    before = (PH.home(cfg) / "X000001.jpg").read_bytes()
    r = PH.update(cfg, {"X000001": "Jan Doe", "X000002": "Sam Roe"}, refresh=("X000001",), get=source({US: PH.PhotoError("down")}))
    assert len(r["errors"]) == 2 and (PH.home(cfg) / "X000001.jpg").read_bytes() == before
    assert "X000002" not in PH.read_manifest(cfg)["unavailable"], "a source being down isn't evidence of no photo"


def test_a_changed_file_is_refused(cfg):
    PH.update(cfg, {"X000001": "Jan Doe"}, get=source({US: jpeg()}))
    (PH.home(cfg) / "X000001.jpg").write_bytes(jpeg(pad=5000))
    assert PH.verify(cfg) == ["X000001: file differs from its record"]


def test_directory_first_senators_try_the_directory_first(cfg):
    pid = next(iter(PH.DIRECTORY_FIRST))
    get = source({US: jpeg(), BIO: jpeg(180, 225)})
    PH.update(cfg, {pid: "Name"}, get=get)
    assert BIO in get.calls[0]


# ---- the real saved photos and the built site ----
@pytest.fixture(scope="module")
def built():
    pages = BS.build(DEFAULT)
    core = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', pages[BS.PAGE].decode(), re.S).group(1))
    return core, pages


def test_every_senator_has_a_photo_or_is_listed_as_unavailable(built):
    core, pages = built
    m = PH.read_manifest(DEFAULT)
    assert PH.verify(DEFAULT) == []
    for s in core["senators"]:
        if s["photo"]:
            assert s["photo"] == f"photos/{s['id']}.jpg" and pages[s["photo"]] == (PH.home(DEFAULT) / f"{s['id']}.jpg").read_bytes()
        else:
            assert s["id"] in m["unavailable"], s["name"]
    assert sum(1 for s in core["senators"] if s["photo"]) >= 100
    seated = [s for s in core["senators"] if s["seated"]]
    assert sum(1 for s in seated if not s["photo"]) <= 2, "only a genuinely missing official photo falls back to initials"


def test_the_checker_catches_a_wrong_or_missing_photo(built):
    core, pages = built
    assert not failed(S.site_photo_checks(DEFAULT, core, pages), "Site: every senator photo")
    one = next(s for s in core["senators"] if s["photo"])
    bad = dict(pages)
    bad[one["photo"]] = b"\xff\xd8\xff" + b"0" * 5000
    assert failed(S.site_photo_checks(DEFAULT, core, bad), "Site: every senator photo")
    swapped = copy.deepcopy(core)
    other = next(s for s in swapped["senators"] if s["photo"] and s["id"] != one["id"])
    next(s for s in swapped["senators"] if s["id"] == one["id"])["photo"] = other["photo"]
    assert failed(S.site_photo_checks(DEFAULT, swapped, pages), "Site: every senator photo")
    hidden = copy.deepcopy(core)
    next(s for s in hidden["senators"] if s["id"] == one["id"])["photo"] = None
    assert failed(S.site_photo_checks(DEFAULT, hidden, pages), "Site: every senator photo"), "a photo we have can't be swapped for initials"


def test_the_page_uses_only_saved_photos():
    body = TEMPLATE[TEMPLATE.index("const photo="):TEMPLATE.index("const badge=")]
    assert "s.photo?" in body and 'src="${esc(s.photo)}"' in body and "http" not in body
    assert 'loading="lazy" decoding="async"' in body
    assert "object-fit:cover" in TEMPLATE and "object-position:50% 15%" in TEMPLATE


def test_photos_appear_in_search_profiles_committees_and_the_senate_view():
    assert "img:photo(s,\"xs\")})" in TEMPLATE and "${r.img||\"\"}" in TEMPLATE        # header search
    assert "img:photo(s,\"xs\")}))" in TEMPLATE                                      # senator pickers
    assert 'photo(s,"big")' in TEMPLATE and "${photo(m.s)}" in TEMPLATE and 'photo(s,"mid")' in TEMPLATE


def test_photos_are_attributed():
    assert "D.photos.sources" in TEMPLATE and "public domain" in TEMPLATE
