"""Current state populations, for weighting the national public centre.

The specification's US_m is the centre of the national electorate. State estimates
have to be weighted by how many people each state holds, and using a fixed census
year makes that weighting drift as people move between states.

Source: U.S. Census Bureau, Vintage 2024 population estimates,
NST-EST2024-ALLDATA.csv. Served as a plain file, so no API key is required and the
fetch stays reproducible.

The Census API endpoint (api.census.gov/data/.../pep/population) returns "Missing
Key" for this query, which is why the published file is used instead.
"""
import csv
from pathlib import Path

USPS = {
 "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA",
 "Colorado":"CO","Connecticut":"CT","Delaware":"DE","District of Columbia":"DC",
 "Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL",
 "Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA",
 "Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN",
 "Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV",
 "New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY",
 "North Carolina":"NC","North Dakota":"ND","Ohio":"OH","Oklahoma":"OK","Oregon":"OR",
 "Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD",
 "Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA",
 "Washington":"WA","West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY",
}


def load_populations(path: Path, year: int = 2024) -> dict[str, int]:
    """Population per state (SUMLEV 040), keyed by USPS code."""
    col = f"POPESTIMATE{year}"
    out: dict[str, int] = {}
    with path.open() as fh:
        for row in csv.DictReader(fh):
            if row.get("SUMLEV") != "040":
                continue
            usps = USPS.get(row["NAME"])
            if usps and row.get(col):
                out[usps] = int(row[col])
    if not out:
        raise ValueError(f"no {col} rows found in {path}")
    return out
