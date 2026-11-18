"""Offline publisher packaging checks; no model, billing or network."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from scripts import prepare_50degrees_publish as P
from civicalign import legislative_sync as S
from test_legislative_sync import drop_files

NOW = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)
MADE = "2026-11-17T20:00:00+00:00"


def source(tmp_path: Path, files: dict | None = None):
    folder = tmp_path / "export"
    folder.mkdir()
    for name, content in (files if files is not None else drop_files(made=MADE)).items():
        (folder / name).write_bytes(content)
    return folder


def test_manifest_matches_existing_importer(tmp_path):
    prepared = tmp_path / "prepared"
    meta = P.prepare(source(tmp_path), prepared, now=NOW)
    assert set(meta["files"]) == set(P.L.FILES)
    assert json.loads((prepared / "manifest.json").read_text()) == meta
    assert S.check_drop(prepared, meta, None, {"A1"}, 119) == []


def test_existing_destination_never_overwritten(tmp_path):
    src = source(tmp_path)
    output = tmp_path / "prepared"
    output.mkdir()
    (output / "safe.txt").write_text("do not overwrite")
    with pytest.raises(ValueError, match="already exists"):
        P.prepare(src, output, now=NOW)
    assert (output / "safe.txt").read_text() == "do not overwrite"


def test_old_export_is_rejected_without_output(tmp_path):
    old = drop_files(made="2026-10-29T14:00:00+00:00")
    target = tmp_path / "output"
    with pytest.raises(ValueError, match="stale"):
        P.prepare(source(tmp_path, old), target, now=NOW)
    assert not target.exists()


def test_future_export_is_rejected(tmp_path):
    future = (NOW + timedelta(days=2)).isoformat()
    with pytest.raises(ValueError, match="future dated"):
        P.prepare(source(tmp_path, drop_files(made=future)), tmp_path / "output", now=NOW)


def test_bad_count_is_rejected_without_output(tmp_path):
    files = drop_files(made=MADE)
    meta = json.loads(files["meta.json"])
    meta["counts"]["bills"] = 999
    files["meta.json"] = json.dumps(meta).encode()
    with pytest.raises(ValueError, match="bill.*count"):
        P.prepare(source(tmp_path, files), tmp_path / "output", now=NOW)
    assert not (tmp_path / "output").exists()


def test_missing_export_file_is_rejected(tmp_path):
    files = drop_files(made=MADE)
    del files["votes.json"]
    with pytest.raises(ValueError, match="votes.json"):
        P.prepare(source(tmp_path, files), tmp_path / "output", now=NOW)


def test_unknown_senator_cross_reference_is_rejected(tmp_path):
    files = drop_files(made=MADE, positions={"119-2-1": {"MISSING": "Yea"}, "119-2-2": {"A1": "Nay"}})
    with pytest.raises(ValueError, match="cross-reference"):
        P.prepare(source(tmp_path, files), tmp_path / "output", now=NOW)


def test_duplicate_votes_are_rejected(tmp_path):
    files = drop_files(made=MADE)
    votes = json.loads(files["votes.json"])
    votes.append(dict(votes[0]))
    files["votes.json"] = json.dumps(votes).encode()
    meta = json.loads(files["meta.json"])
    meta["counts"]["votes"] = len(votes)
    files["meta.json"] = json.dumps(meta).encode()
    with pytest.raises(ValueError, match="duplicate IDs"):
        P.prepare(source(tmp_path, files), tmp_path / "output", now=NOW)


def test_invalid_json_is_rejected(tmp_path):
    files = drop_files(made=MADE)
    files["bills.json"] = b"oops"
    with pytest.raises(ValueError, match="invalid JSON"):
        P.prepare(source(tmp_path, files), tmp_path / "output", now=NOW)


def test_no_network_or_model_client():
    code = Path(P.__file__).read_text()
    for banned in ("openai", "anthropic", "requests.", "urllib", "subprocess", "os.environ"):
        assert banned not in code.lower()
