"""Package an EXISTING 50degrees export for CivicAlign's approved publisher.

No bill generation, AI calls, network requests, deployment or credentials.
The output manifest is compatible with civicalign.legislative_sync.
"""
import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from civicalign import legislative as L

MAX_FILE_BYTES = 200_000_000


def verify_source(source: Path, congress: int, now: datetime | None = None,
                  max_age_days: int = 14) -> dict:
    """Return a publisher manifest only for a consistent, fresh export."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or max_age_days < 0:
        raise ValueError("timezone-aware now and nonnegative max_age_days required")
    data = {}
    paths = {}
    for name in L.FILES:
        file = source / name
        if file.is_symlink() or not file.is_file():
            raise ValueError(f"required export file missing or symlinked: {name}")
        if file.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"oversized export file: {name}")
        paths[name] = file
        if name.endswith(".json"):
            try:
                data[name[:-5]] = json.loads(file.read_text(encoding="utf-8"))
            except (UnicodeError, json.JSONDecodeError) as e:
                raise ValueError(f"invalid JSON in {name}") from e

    meta = data["meta"]
    if not isinstance(meta, dict) or meta.get("congress") != congress:
        raise ValueError("export has the wrong Congress")
    try:
        generated = datetime.fromisoformat(meta["generated_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError, KeyError) as e:
        raise ValueError("export has no valid generated_at timestamp") from e
    if generated.tzinfo is None:
        raise ValueError("generated_at must include a UTC offset")
    age = now - generated
    if age < -timedelta(minutes=5):
        raise ValueError("export is future dated")
    if age > timedelta(days=max_age_days):
        raise ValueError(f"export is stale (older than {max_age_days} days)")
    if not isinstance(meta.get("counts"), dict):
        raise ValueError("export is missing declared counts")
    for key in ("senators", "votes", "bills", "committee_votes", "nominations"):
        records = data[key]
        if not isinstance(records, list):
            raise ValueError(f"{key}.json must be a list")
        if meta["counts"].get(key) != len(records):
            raise ValueError(f"declared {key} count does not match file")
        if key != "committee_votes":
            ids = [r["id"] for r in records]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{key}.json contains duplicate IDs")
    if not isinstance(data["positions"], dict):
        raise ValueError("positions.json must be an object")
    if meta["counts"].get("positions") != len(data["positions"]):
        raise ValueError("declared positions count does not match file")
    try:
        known = {r["id"] for r in data["senators"]}
        errors = L.problems(data, known)
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError("export has an unexpected data schema") from e
    if errors:
        raise ValueError("export cross-reference failure: " + "; ".join(errors[:4]))
    return {
        "congress": congress,
        "generated_at": meta["generated_at"],
        "files": {name: hashlib.sha256(paths[name].read_bytes()).hexdigest() for name in L.FILES},
    }


def prepare(source: Path, output: Path, congress: int = 119,
            now: datetime | None = None, max_age_days: int = 14) -> dict:
    """Create a new upload directory, manifest last, never overwrite."""
    source, output = Path(source), Path(output)
    manifest = verify_source(source, congress, now, max_age_days)
    if output.exists():
        raise ValueError(f"output already exists; refusing overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".civicalign-publisher-", dir=output.parent))
    try:
        for name in L.FILES:
            shutil.copyfile(source / name, tmp / name)
        for name, digest in manifest["files"].items():
            if hashlib.sha256((tmp / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"copy hash mismatch for {name}")
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        tmp.rename(output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--congress", type=int, default=119)
    p.add_argument("--max-age-days", type=int, default=14)
    args = p.parse_args()
    manifest = prepare(args.source, args.output, args.congress, max_age_days=args.max_age_days)
    print(f"Prepared {len(manifest['files'])} source-checked files at {args.output}")
    print("Not uploaded or approved; configure an authenticated HTTPS publisher separately.")


if __name__ == "__main__":
    main()
