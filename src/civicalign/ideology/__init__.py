"""Engine B: institutional and ideological context (Pillars 4, 5 and 6).

Pillar 4  where a senator sits relative to their state's estimated centre
Pillar 5  where the Senate sits relative to the national electorate, and to a
          population-weighted counterfactual of itself
Pillar 6  where each standing committee sits relative to the Senate and the
          national electorate

Engine A (what a senator actually voted for and what the vote meant) lives in
civicalign.explain and civicalign.evaluation. Nothing in this package imports
from them, and nothing here explains an individual vote.

Step 1 (this commit): versioned input records, an append-only store, and the
ingest from the verified source snapshot. No metric is computed yet.
"""
