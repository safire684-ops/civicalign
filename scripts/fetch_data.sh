#!/usr/bin/env bash
# Refresh raw source data and record provenance.
#
# Voteview REVISES past scores when it re-estimates, so a number cached last
# month may no longer be the published number. Every refresh is stamped.
set -euo pipefail

cd "$(dirname "$0")/.."
RAW="data/raw"
mkdir -p "$RAW"

fetch () {
  local url="$1" name="$2"
  echo "fetching $name"
  curl -sSfL --max-time 120 -o "$RAW/$name" "$url"
  local sum
  sum="$(shasum -a 256 "$RAW/$name" | cut -d' ' -f1)"
  printf '%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$name" "$sum" "$url" \
    >> "$RAW/PROVENANCE.tsv"
}

fetch "https://voteview.com/static/data/out/members/HSall_members.csv" \
      "HSall_members.csv"
# MIT Election Data and Science Lab, U.S. President 1976-2024.
# doi:10.7910/DVN/42MVDX. Reproduces official national totals to within a few
# dozen votes; a county-level alternative understated CA 2016 Democrats by 1.4M.
fetch "https://dataverse.harvard.edu/api/access/datafile/13887042" \
      "mit_president_1976_2024.csv"
# Tausanovitch & Warshaw, American Ideology Project v2022, doi:10.7910/DVN/BQKU4M.
# The bridged joint-scaling estimates: state publics on the SAME ideological scale
# as congressional roll-call scores, which is what makes Pillar 4's absolute
# distance a legal subtraction.
fetch "https://dataverse.harvard.edu/api/access/datafile/6690212" \
      "aip_states_ideology_v2022a.tab"
# U.S. Census Bureau vintage 2024 state population estimates, for weighting US_m.
# The published file is used rather than api.census.gov, which requires a key.
fetch "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/state/totals/NST-EST2024-ALLDATA.csv" \
      "NST-EST2024-ALLDATA.csv"
fetch "https://unitedstates.github.io/congress-legislators/legislators-current.json" \
      "legislators-current.json"
fetch "https://unitedstates.github.io/congress-legislators/committee-membership-current.json" \
      "committee-membership-current.json"

echo "done. provenance appended to $RAW/PROVENANCE.tsv"
