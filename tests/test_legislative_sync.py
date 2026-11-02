"""Importing a new legislative drop unattended. Every bad drop must leave the last one in place."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from civicalign import legislative as L
from civicalign import legislative_sync as S
from civicalign.config import DEFAULT

ROOT = Path(__file__).resolve().parent.parent
URL = "https://publisher.example/drops/119"


def drop_files(made="2026-11-05T14:00:00+00:00", votes=("119-2-1", "119-2-2"), **over):
    files = {"senators": [{"id": "A1"}],
             "votes": [{"id": v, "bill": None, "nominations": []} for v in votes],
             "positions": {v: {"A1": "Yea"} for v in votes},
             "bills": [{"id": "s1", "votes": list(votes)[:1]}],
             "committee_votes": [{"id": "c1"}],
             "nominations": []}
    files.update(over)
    counts = {k: len(v) for k, v in files.items()}
    files["meta"] = {"congress": 119, "generated_at": made, "counts": counts}
    out = {f"{k}.json": json.dumps(v).encode() for k, v in files.items()}
    out["README.md"] = b"readme"
    return out


def manifest_of(files, made="2026-11-05T14:00:00+00:00", congress=119):
    return {"congress": congress, "generated_at": made, "files": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}


def publish(monkeypatch, files, manifest=None):
    served = {URL + "/" + n: b for n, b in files.items()}
    served[URL + "/manifest.json"] = json.dumps(manifest or manifest_of(files)).encode()
    calls = []
    def get(url, token):
        calls.append((url, token))
        if url not in served:
            raise S.urllib.error.URLError("no such file")
        return served[url]
    monkeypatch.setattr(S, "_get", get)
    return calls


@pytest.fixture
def cfg(tmp_path):
    c = replace(DEFAULT, ideology_dir=tmp_path / "data" / "ideology", raw_dir=tmp_path / "data" / "raw")
    return c


def seed(cfg, tmp_path, **kw):
    """A valid earlier drop."""
    files = drop_files(made="2026-10-29T14:00:00+00:00", **kw)
    folder = tmp_path / "seed"
    folder.mkdir()
    for n, b in files.items():
        (folder / n).write_bytes(b)
    return L.import_drop(folder, cfg)


def run(cfg, url=URL, token=None):
    return S.sync(cfg, url=url, token=token, engine_ids={"A1"})


def test_no_publisher_changes_nothing_and_says_what_is_missing(cfg, tmp_path):
    dest = seed(cfg, tmp_path)
    result = run(cfg, url="")
    assert result["state"] == "not_configured" and "No approved publisher" in result["detail"]
    assert L.latest_dir(cfg) == dest


def test_a_good_drop_is_imported_with_its_manifest(cfg, tmp_path, monkeypatch):
    seed(cfg, tmp_path)
    publish(monkeypatch, drop_files(votes=("119-2-1", "119-2-2", "119-2-3")))
    result = run(cfg)
    assert result["state"] == "imported" and result["latest_drop"] == "2026-11-05T14:00:00+00:00"
    assert L.latest_dir(cfg).name == "2026-11-05" and len(L.load(cfg)["votes"]) == 3


def test_the_token_is_sent_only_to_the_publisher(cfg, tmp_path, monkeypatch):
    seed(cfg, tmp_path)
    calls = publish(monkeypatch, drop_files())
    run(cfg, token="secret")
    assert calls and all(u.startswith(URL) and t == "secret" for u, t in calls)


def test_the_same_drop_again_is_current(cfg, tmp_path, monkeypatch):
    seed(cfg, tmp_path)
    publish(monkeypatch, drop_files(made="2026-10-29T14:00:00+00:00"), manifest_of(drop_files(made="2026-10-29T14:00:00+00:00"), made="2026-10-29T14:00:00+00:00"))
    assert run(cfg)["state"] == "current"


def rejected(cfg, tmp_path, monkeypatch, files, manifest=None, words=""):
    before = seed(cfg, tmp_path)
    publish(monkeypatch, files, manifest)
    result = run(cfg)
    assert result["state"] == "rejected", result
    assert words in result["detail"], result["detail"]
    assert L.latest_dir(cfg) == before, "the last valid drop must stay in place"
    assert len(list(L.root(cfg).glob("*"))) == 1
    return result


def test_a_file_that_doesnt_match_its_hash_is_rejected(cfg, tmp_path, monkeypatch):
    files = drop_files()
    manifest = manifest_of(files)
    files["votes.json"] = files["votes.json"] + b" "
    rejected(cfg, tmp_path, monkeypatch, files, manifest, "votes.json does not match")


def test_a_missing_file_is_rejected(cfg, tmp_path, monkeypatch):
    files = drop_files()
    manifest = manifest_of(files)
    del manifest["files"]["bills.json"]
    rejected(cfg, tmp_path, monkeypatch, files, manifest, "not the expected set")


def test_counts_that_disagree_are_rejected(cfg, tmp_path, monkeypatch):
    files = drop_files()
    meta = json.loads(files["meta.json"])
    meta["counts"]["votes"] = 99
    files["meta.json"] = json.dumps(meta).encode()
    rejected(cfg, tmp_path, monkeypatch, files, None, "says 99 votes")


def test_ids_that_dont_join_are_rejected(cfg, tmp_path, monkeypatch):
    files = drop_files(votes=("119-2-1", "119-2-2"), senators=[{"id": "A1"}], positions={"119-2-1": {"Z9": "Yea"}, "119-2-2": {"A1": "Yea"}})
    rejected(cfg, tmp_path, monkeypatch, files, None, "unknown senator Z9")


def test_a_senator_engine_b_doesnt_know_is_rejected(cfg, tmp_path, monkeypatch):
    seed(cfg, tmp_path)
    publish(monkeypatch, drop_files())
    result = S.sync(cfg, url=URL, engine_ids={"OTHER"})
    assert result["state"] == "rejected" and "A1 is not in Engine B" in result["detail"]


def test_losing_a_vote_is_rejected(cfg, tmp_path, monkeypatch):
    rejected(cfg, tmp_path, monkeypatch, drop_files(votes=("119-2-1",)), None, "votes in the last drop are missing")


def test_fewer_committee_votes_is_rejected(cfg, tmp_path, monkeypatch):
    before = seed(cfg, tmp_path, committee_votes=[{"id": "c1"}, {"id": "c2"}])
    publish(monkeypatch, drop_files())
    result = run(cfg)
    assert result["state"] == "rejected" and "committee votes fell" in result["detail"] and L.latest_dir(cfg) == before


def test_an_older_drop_is_rejected(cfg, tmp_path, monkeypatch):
    made = "2026-10-01T14:00:00+00:00"
    rejected(cfg, tmp_path, monkeypatch, drop_files(made=made), manifest_of(drop_files(made=made), made=made), "not newer")


def test_another_congress_is_rejected(cfg, tmp_path, monkeypatch):
    files = drop_files()
    rejected(cfg, tmp_path, monkeypatch, files, manifest_of(files, congress=120), "Congress 120")


def test_a_file_that_isnt_json_is_rejected(cfg, tmp_path, monkeypatch):
    files = drop_files()
    files["votes.json"] = b"<html>error</html>"
    rejected(cfg, tmp_path, monkeypatch, files, None, "not valid JSON")


def test_plain_http_is_rejected(cfg, tmp_path):
    seed(cfg, tmp_path)
    assert run(cfg, url="http://publisher.example/drops")["state"] == "rejected"


def test_an_unreachable_publisher_changes_nothing(cfg, tmp_path, monkeypatch):
    before = seed(cfg, tmp_path)
    def down(url, token):
        raise S.urllib.error.URLError("down")
    monkeypatch.setattr(S, "_get", down)
    assert run(cfg)["state"] == "unreachable" and L.latest_dir(cfg) == before


def test_a_manifest_that_isnt_json_changes_nothing(cfg, tmp_path, monkeypatch):
    before = seed(cfg, tmp_path)
    monkeypatch.setattr(S, "_get", lambda url, token: b"<html>")
    assert run(cfg)["state"] == "unreachable" and L.latest_dir(cfg) == before


def test_an_extra_file_named_by_the_publisher_is_never_written(cfg, tmp_path, monkeypatch):
    files = drop_files()
    manifest = manifest_of(files)
    manifest["files"]["../../evil.json"] = "0" * 64
    rejected(cfg, tmp_path, monkeypatch, files, manifest, "not the expected set")
    assert not (tmp_path / "evil.json").exists()


def test_the_workflow_reads_the_publisher_from_settings_not_the_code():
    y = (ROOT / ".github" / "workflows" / "update.yml").read_text()
    assert "vars.CIVICALIGN_DROP_URL" in y and "secrets.CIVICALIGN_DROP_TOKEN" in y
    assert y.index("civicalign.legislative_sync") < y.index("civicalign.record_votes") < y.index("-m civicalign.build_pages")
    assert "data/legislative" in next(l for l in y.splitlines() if "git add demo/" in l)
