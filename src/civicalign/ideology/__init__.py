"""Engine B: institutional and ideological context (Pillars 4, 5 and 6).

Pillar 4  each senator's Voteview nominate_dim1 score beside their state public's
          survey estimate (separate scales; no senator-to-state distance while
          the bridge is NONE), with three visual-only reference anchors
Pillar 5  the Senate mean with each senator counted equally against the
          population-weighted mean, and their difference (primary); the medians
          as a secondary comparison; the national public estimate unresolved
Pillar 6  each standing committee's median and its drift from the Senate median

records/store/ingest   versioned, append-only inputs from the verified snapshot
bridge/national        the bridge registry (none-v0, NONE) and the unresolved national estimate
pillars/compute        the calculations and the versioned, write-once results
anchors/methodology    the reference anchors and the registry behind every displayed number

Engine A (what a senator actually voted for) lives in civicalign.explain and
civicalign.evaluation. Nothing in this package imports from them, and nothing
here explains an individual vote. See docs/ENGINE_B_DATA_FLOW.md.
"""
