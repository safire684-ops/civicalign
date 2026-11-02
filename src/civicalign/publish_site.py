"""Arrange the folder GitHub Pages publishes, once every gate has passed.

    PYTHONPATH=src python -m civicalign.publish_site [--source DIR] [--out DIR]

Copies demo/ to _site/, then in the copy only moves the old page to
senator-check-original.html, byte for byte, and puts a redirect to the integrated site at
senator-check.html. demo/ is not changed, so the tests, the supervisor and the daily commit
keep reading the page they always read. Anything unexpected stops the job before upload.
"""
import argparse
import shutil
import sys
from pathlib import Path

from .build_pages import OUT

SITE = "civicalign.html"
OLD = "senator-check.html"
BACKUP = "senator-check-original.html"
PUBLISH = OUT.parent / "_site"
REDIRECT = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CivicAlign</title>
<link rel="canonical" href="{SITE}">
<script>
var old={{senators:"#/senators",senate:"#/senate",committees:"#/committees",how:"#/about"}};
location.replace("{SITE}"+(old[location.hash.slice(1)]||""));
</script>
<noscript><meta http-equiv="refresh" content="0; url={SITE}"></noscript>
</head><body><p>CivicAlign has moved: <a href="{SITE}">open the site</a>.</p></body></html>
"""


def arrange(source: Path, out: Path) -> None:
    for name in (SITE, OLD, "index.html"):
        if not (source / name).is_file():
            raise SystemExit(f"publish_site: {source / name} is missing")
    if f"url={SITE}" not in (source / "index.html").read_text():
        raise SystemExit(f"publish_site: index.html does not open {SITE}")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(source, out, ignore=shutil.ignore_patterns(".DS_Store"))
    (out / OLD).rename(out / BACKUP)
    (out / OLD).write_text(REDIRECT)
    if (out / BACKUP).read_bytes() != (source / OLD).read_bytes():
        raise SystemExit("publish_site: the backup differs from the verified page")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=OUT)
    ap.add_argument("--out", type=Path, default=PUBLISH)
    args = ap.parse_args()
    arrange(args.source, args.out)
    print(f"{args.out}: {OLD} redirects to {SITE}; the original is at {BACKUP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
