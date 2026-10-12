"""All eight committee measure types are counted without losing their identifiers."""
import dataclasses
import hashlib
import json
import zipfile

from civicalign.config import DEFAULT
from civicalign.ideology import committee_measures as CM
from civicalign.agents import supervisor as S


def _xml(typ, num, activities):
    acts = "".join(f"<item><name>{name}</name><date>2026-09-01</date></item>" for name in activities)
    return (f"<billStatus><bill><congress>119</congress><type>{typ.upper()}</type>"
            f"<number>{num}</number><title>Example {typ} {num}</title>"
            f"<committees><item><systemCode>ssra00</systemCode><chamber>Senate</chamber>"
            f"<activities>{acts}</activities></item></committees>"
            f"</bill></billStatus>").encode()


def _fixture(tmp_path):
    entries = []
    for i, typ in enumerate(CM.TYPES, start=1):
        file = tmp_path / f"BILLSTATUS-119-{typ}.zip"
        with zipfile.ZipFile(file, "w") as z:
            z.writestr(f"{typ}{i}.xml", _xml(typ, i, ["Referred To", "Reported By"] if i % 2 else ["Referred To"]))
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        entries.append({"file": file.name, "sha256": digest, "content_key": digest,
                        "content_changed_utc": "2026-09-01T00:00:00Z"})
    (tmp_path / "SNAPSHOT.json").write_text(json.dumps({"accepted": True, "sources": entries}))
    return dataclasses.replace(DEFAULT, raw_dir=tmp_path)


def test_all_eight_types_are_counted_and_traced(tmp_path):
    cfg = _fixture(tmp_path)
    result = CM.totals(cfg, ["SSRA"])
    assert result["available"]
    c = result["committees"]["SSRA"]
    assert len(c["referred"]) == 8
    assert len(c["reported"]) == 4
    assert len(c["reported_without_referral"]) == 0
    assert {typ for typ, v in c["by_type"].items() if v["referred"]} == set(CM.TYPES)
    assert len(result["measures"]) == 8
    page = {"p6": {"committees": [{"code": "SSRA", "all_measures": c}],
                   "measure_meta": {"available": True, "versions": result["versions"]}}}
    checks = S.eb_all_measure_checks(cfg, page)
    assert all(x.ok for x in checks), checks
    page["p6"]["committees"][0]["all_measures"]["by_type"]["hr"]["referred"] = []
    checks = S.eb_all_measure_checks(cfg, page)
    assert any(not x.ok for x in checks), checks


def test_missing_verified_archive_is_not_zero_activity(tmp_path):
    cfg = _fixture(tmp_path)
    (tmp_path / "BILLSTATUS-119-hres.zip").unlink()
    result = CM.totals(cfg, ["SSRA"])
    assert not result["available"] and not result["committees"]
    page = {"p6": {"committees": [{"code": "SSRA", "all_measures": None}],
                   "measure_meta": {"available": False, "versions": {}, "reason": result["reason"]}}}
    assert all(x.ok for x in S.eb_all_measure_checks(cfg, page))
