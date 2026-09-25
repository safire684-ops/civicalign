# FIXTURES — not real data

Every file in this folder is an invented test fixture for the Pillars 4-6
ingest tests (`tests/test_ideology_records.py`). Names, ids, states and scores
are made up: senators are "FIXTURE Senator ...", bioguide ids start with `FX`,
Voteview ids with `9000`, states are the non-existent codes `ZZ`, `ZY`, `ZX`.
The tests copy these files into a temporary folder under the real file names,
write a snapshot record whose entries carry `"fixture": true`, and check that
every ingested record carries `fixture: true`. Nothing here is ever written to
`data/ideology/`.
