"""python -m civicalign.agents  --  refresh every source as one snapshot, or not at all."""
import sys

from ..config import DEFAULT
from .base import run_snapshot
from .sources import all_agents


def main() -> int:
    agents = all_agents()
    snap = run_snapshot(agents, DEFAULT.raw_dir)
    print(f"CivicAlign update run  {snap.run_utc}\n")
    for r in snap.results:
        print(r.line())
    print(f"\n  {snap.summary()}")
    if not snap.accepted:
        print("\n  The site is not rebuilt from a partial refresh. Fix the failing source")
        print("  and re-run; until then the previously verified site stays live.")
        return 1
    if snap.changed:
        print("\n  Data changed. The tests, rebuild and supervisor decide whether it publishes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
