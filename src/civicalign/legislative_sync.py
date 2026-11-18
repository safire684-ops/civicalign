"""Import a new legislative drop from the approved publisher, unattended.

    PYTHONPATH=src python -m civicalign.legislative_sync

The publisher is set by CIVICALIGN_DROP_URL, with an optional CIVICALIGN_DROP_TOKEN sent as a
bearer token. It must publish manifest.json beside the drop's files:

    {"congress": 119, "generated_at": "2026-11-05T14:00:00+00:00", "files": {"votes.json": "<sha256>", ...}}

With no publisher set, this reports not_configured and changes nothing. No other source is
ever used in its place. A drop is downloaded to a temporary folder and imported only if every
check passes: each file's hash, the counts in meta.json, every id join, and coverage (a new
drop has to keep every vote, bill and nomination the last one had). A rejected or unreachable
drop leaves the last valid drop in place. The site keeps building from it, and the health
report says so. The outcome is written to data/processed/drop_sync.json.
"""
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import legislative as L
from .config import DEFAULT, Config
from .ideology import bills as BL

LISTS = ("senators", "votes", "bills", "committee_votes", "nominations")
MAX_FILE_BYTES = 200_000_000


def status_path(cfg: Config = DEFAULT) -> Path:
    return cfg.raw_dir.parent / "processed" / "drop_sync.json"


def _get(url: str, token: str | None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "CivicAlign data pipeline", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(request, timeout=120) as r:
        body = r.read(MAX_FILE_BYTES + 1)
    if len(body) > MAX_FILE_BYTES:
        raise L.LegislativeError(f"{url} is larger than {MAX_FILE_BYTES} bytes")
    return body


def check_drop(folder: Path, manifest: dict, previous: dict | None, engine_ids: set[str], congress: int) -> list[str]:
    """Every reason not to import this drop. Empty means it may be imported."""
    wrong = []
    if manifest.get("congress") != congress:
        wrong.append(f"the drop is for Congress {manifest.get('congress')}, this build is {congress}")
    if set(manifest.get("files", {})) != set(L.FILES):
        wrong.append(f"the drop's files are not the expected set: {sorted(set(manifest.get('files', {})) ^ set(L.FILES))}")
    for name, want in manifest.get("files", {}).items():
        path = folder / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != want:
            wrong.append(f"{name} does not match the publisher's manifest")
    if wrong:
        return wrong
    try:
        drop = {n[:-5]: json.loads((folder / n).read_text()) for n in L.FILES if n.endswith(".json")}
    except json.JSONDecodeError as e:
        return [f"a file is not valid JSON: {e}"]
    meta = drop["meta"]
    if meta.get("generated_at") != manifest.get("generated_at") or meta.get("congress") != congress:
        wrong.append("meta.json disagrees with the publisher's manifest")
    for name in LISTS + ("positions",):
        if meta.get("counts", {}).get(name) != len(drop[name]):
            wrong.append(f"meta.json says {meta.get('counts', {}).get(name)} {name}, the file has {len(drop[name])}")
    wrong += L.problems(drop, engine_ids)
    if previous is not None:
        if str(manifest.get("generated_at")) <= previous["manifest"]["generated_at"]:
            wrong.append(f"the drop made {manifest.get('generated_at')} is not newer than the one we have, {previous['manifest']['generated_at']}")
        for name in ("votes", "bills", "nominations"):
            gone = {x["id"] for x in previous[name]} - {x["id"] for x in drop[name]}
            if gone:
                wrong.append(f"{len(gone)} {name} in the last drop are missing from this one, such as {sorted(gone)[0]}")
        if len(drop["committee_votes"]) < len(previous["committee_votes"]):
            wrong.append(f"committee votes fell from {len(previous['committee_votes'])} to {len(drop['committee_votes'])}")
    return wrong


def sync(cfg: Config = DEFAULT, url: str | None = None, token: str | None = None, engine_ids: set[str] | None = None) -> dict:
    """Fetch and import if there is something new. Never raises for a bad or missing drop."""
    url = url if url is not None else os.environ.get("CIVICALIGN_DROP_URL", "").strip()
    token = token if token is not None else os.environ.get("CIVICALIGN_DROP_TOKEN", "").strip() or None
    previous = L.load(cfg) if any((p / "MANIFEST.json").exists() for p in L.root(cfg).glob("*")) else None
    out = {"checked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "latest_drop": previous["manifest"]["generated_at"] if previous else None}
    if not url:
        return {**out, "state": "not_configured", "detail": "No approved publisher is set, so new drops still have to be imported by hand."}
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1")):
        return {**out, "state": "rejected", "detail": "The publisher address must use https."}
    base = url.rstrip("/") + "/"
    try:
        manifest = json.loads(_get(base + "manifest.json", token))
        if previous and manifest.get("generated_at") == previous["manifest"]["generated_at"]:
            return {**out, "state": "current", "detail": "The publisher has nothing newer."}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in manifest.get("files", {}):
                if name in L.FILES:
                    (folder / name).write_bytes(_get(base + urllib.parse.quote(name), token))
            ids = engine_ids if engine_ids is not None else set(BL.current_sponsor_scores(cfg))
            wrong = check_drop(folder, manifest, previous, ids, cfg.congress)
            if wrong:
                return {**out, "state": "rejected", "detail": "; ".join(wrong[:8])}
            dest = L.import_drop(folder, cfg)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, AttributeError, L.LegislativeError) as e:
        return {**out, "state": "unreachable", "detail": f"{type(e).__name__}: {e}"[:300]}
    return {**out, "state": "imported", "latest_drop": manifest["generated_at"], "detail": f"Imported into {dest.name}."}


def main() -> int:
    result = sync(DEFAULT)
    path = status_path(DEFAULT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1) + "\n")
    print(f"legislative drop: {result['state']}: {result['detail']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
