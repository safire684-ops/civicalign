"""Official senator photos, kept with the site so they load fast and can't disappear.

    PYTHONPATH=src python -m civicalign.photos [--refresh BIOGUIDE ...]

For every senator the site shows (the current roster and everyone in the legislative files), a photo
is downloaded once from the first source that has one, checked to be a real portrait-shaped JPEG,
and saved as data/photos/<bioguide>.jpg with its source, URL, checksum and size in data/photos/PHOTOS.json.
Saved photos aren't downloaded again unless --refresh names them. A senator no source has is listed as
unavailable and asked for again on every run; the site shows their initials until a photo exists.
A network failure changes nothing that was saved.
"""
import argparse
import hashlib
import json
import struct
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import legislative as L
from .config import DEFAULT, Config

USER_AGENT = "CivicAlign data pipeline (https://github.com/safire684-ops/civicalign)"
# In order of preference. Both are official portraits of members of Congress, in the public domain.
SOURCES = (
    ("unitedstates/images (official portraits from the Government Publishing Office's Member Guide)",
     "https://unitedstates.github.io/images/congress/225x275/{id}.jpg"),
    ("Biographical Directory of the United States Congress",
     "https://bioguide.congress.gov/bioguide/photo/{initial}/{id}.jpg"),
)
MIN_BYTES = 3_000
# Senators whose Member Guide copy is a wide or informal shot (the face is tiny in a small circle). For them the
# Biographical Directory's official portrait, framed like everyone else's, is tried first. Checked by eye 2026-11-08.
DIRECTORY_FIRST = {"B001299": "James Banks", "K000377": "Mark Kelly", "M001198": "Roger Marshall"}


class PhotoError(Exception):
    pass


def home(cfg: Config = DEFAULT) -> Path:
    return cfg.ideology_dir.parent / "photos"


def manifest_path(cfg: Config = DEFAULT) -> Path:
    return home(cfg) / "PHOTOS.json"


def read_manifest(cfg: Config = DEFAULT) -> dict:
    p = manifest_path(cfg)
    return json.loads(p.read_text()) if p.exists() else {"photos": {}, "unavailable": {}}


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a JPEG's frame header, or None if the bytes aren't a JPEG."""
    if data[:3] != b"\xff\xd8\xff":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + length
    return None


def problem(data: bytes | None) -> str | None:
    """Why these bytes aren't a usable portrait, or None if they are."""
    if not data:
        return "no file"
    size = jpeg_size(data)
    if size is None:
        return "not a JPEG"
    if len(data) < MIN_BYTES:
        return "too small to be a photo"
    w, h = size
    if w < 100 or h < 120 or h < w:
        return f"not portrait-shaped ({w}x{h})"
    return None


def fetch(url: str) -> bytes | None:
    """The bytes at url, or None when the source has no such file. Other failures raise PhotoError."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return None
            if attempt == 2:
                raise PhotoError(f"{url}: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == 2:
                raise PhotoError(f"{url}: {e}") from e
        time.sleep(2 ** attempt)
    return None


def wanted(cfg: Config = DEFAULT) -> dict[str, str]:
    """bioguide -> name for every senator the site shows: the current roster and the legislative files."""
    out = {}
    for m in json.loads(cfg.roster_json.read_text()):
        if m["terms"][-1]["type"] == "sen":
            out[m["id"]["bioguide"]] = m["name"].get("official_full") or f"{m['name']['first']} {m['name']['last']}"
    for s in L.load(cfg)["senators"]:
        out.setdefault(s["id"], s["name"])
    return dict(sorted(out.items()))


def update(cfg: Config = DEFAULT, people: dict[str, str] | None = None, refresh: tuple[str, ...] = (), get=fetch,
           now: datetime | None = None) -> dict:
    """Fill in missing photos. Returns {"saved": [...], "unavailable": [...], "errors": [...]}."""
    people = wanted(cfg) if people is None else people
    today = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    m = read_manifest(cfg)
    folder = home(cfg)
    folder.mkdir(parents=True, exist_ok=True)
    saved, errors = [], []
    for pid, name in people.items():
        if pid in m["photos"] and pid not in refresh and (folder / f"{pid}.jpg").exists():
            continue
        tried, found = [], None
        try:
            for label, pattern in (SOURCES[::-1] if pid in DIRECTORY_FIRST else SOURCES):
                url = pattern.format(id=pid, initial=pid[0])
                data = get(url)
                why = problem(data)
                tried.append({"url": url, "result": why or "ok"})
                if why is None:
                    found = (label, url, data)
                    break
        except PhotoError as e:
            errors.append(f"{pid}: {e}")
            continue                                # keep whatever was saved before
        if found:
            label, url, data = found
            w, h = jpeg_size(data)
            (folder / f"{pid}.jpg").write_bytes(data)
            m["photos"][pid] = {"name": name, "source": label, "url": url, "sha256": hashlib.sha256(data).hexdigest(),
                                "bytes": len(data), "width": w, "height": h, "retrieved": today}
            m["unavailable"].pop(pid, None)
            saved.append(pid)
        else:
            m["unavailable"][pid] = {"name": name, "since": m["unavailable"].get(pid, {}).get("since", today), "tried": tried}
    for pid in list(m["unavailable"]):
        if pid not in people:
            m["unavailable"].pop(pid)
    m["sources"] = [label for label, _ in SOURCES]
    m["photos"] = dict(sorted(m["photos"].items()))
    m["unavailable"] = dict(sorted(m["unavailable"].items()))
    manifest_path(cfg).write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")
    return {"saved": saved, "unavailable": sorted(m["unavailable"]), "errors": errors}


def verify(cfg: Config = DEFAULT) -> list[str]:
    """Every listed photo is on disk, unchanged and still a usable portrait."""
    m, folder, bad = read_manifest(cfg), home(cfg), []
    for pid, p in m["photos"].items():
        f = folder / f"{pid}.jpg"
        if not f.exists():
            bad.append(f"{pid}: file missing")
            continue
        data = f.read_bytes()
        if hashlib.sha256(data).hexdigest() != p["sha256"]:
            bad.append(f"{pid}: file differs from its record")
        elif problem(data):
            bad.append(f"{pid}: {problem(data)}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", nargs="*", default=[], help="download these senators' photos again")
    a = ap.parse_args()
    r = update(DEFAULT, refresh=tuple(a.refresh))
    bad = verify(DEFAULT)
    m = read_manifest(DEFAULT)
    print(f"photos: {len(m['photos'])} saved ({len(r['saved'])} new), {len(r['unavailable'])} with no official photo"
          + (f": {', '.join(r['unavailable'])}" if r["unavailable"] else ""))
    for e in r["errors"]:
        print(f"  couldn't reach a photo source, kept what was saved: {e}")
    if bad:
        print("PHOTOS REFUSED: " + "; ".join(bad), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
