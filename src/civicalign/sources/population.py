"""State names to USPS codes, for reading the Census state population file.

The Census file (Vintage 2024 NST-EST2024-ALLDATA.csv) names states in full;
the Pillars 4-6 ingest (ideology/ingest.py) and the page builder map them to
two-letter codes with this table. The file is read by ideology/ingest.py.
"""
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
