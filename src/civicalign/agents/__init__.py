"""Single-purpose update jobs.

Each agent owns ONE source, and does the same four things: fetch it, check the
result is sane, write it only if so, and report what happened. Nothing is
half-updated: a source that fails validation leaves the previous good copy in
place, so the site keeps serving yesterday's correct numbers rather than today's
broken ones.

They are independent on purpose. Voteview revising scores has nothing to do with
the Census publishing new population estimates, so a failure in one must not stop
the other. Run them all with `scripts/update.sh`.
"""
from .base import Agent, Result, run_all

__all__ = ["Agent", "Result", "run_all"]
