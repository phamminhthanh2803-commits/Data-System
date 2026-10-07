"""Smoke test with a longer voyage (2016-2025) spanning many regions."""
from route import Waypoint, render
from ports import resolve_port

# Simulated 9-year voyage hitting many distinct regions
rows = [
    ("Dec 2016", "Australia / New Guinea Pacific",  "MT"),
    ("Mar 2017", "SE Asia",                          "MT"),
    ("Jul 2017", "Gulf of Mexico",                   "Both"),
    ("Nov 2017", "US East Coast",                    "MT"),
    ("Feb 2018", "Europe",                           "VT"),
    ("Jun 2018", "Mediterranean",                    "MT"),
    ("Oct 2018", "Suez",                             "MT"),
    ("Dec 2018", "Red Sea",                          "VT"),
    ("Mar 2019", "Persian Gulf",                     "Both"),
    ("Jul 2019", "India",                            "MT"),
    ("Oct 2019", "South Asia",                       "MT"),
    ("Jan 2020", "SE Asia",                          "Both"),
    ("Apr 2020", "East Asia",                        "MT"),
    ("Aug 2020", "Japan",                            "MT"),
    ("Dec 2020", "North Pacific",                    "VT"),
    ("Mar 2021", "US West Coast",                    "Both"),
    ("Jun 2021", "Panama",                           "MT"),
    ("Sep 2021", "Caribbean",                        "MT"),
    ("Dec 2021", "South America East Coast",         "VT"),
    ("Apr 2022", "West Africa",                      "MT"),
    ("Aug 2022", "South Africa",                     "MT"),
    ("Dec 2022", "East Africa",                      "Both"),
    ("Mar 2023", "Indian Ocean",                     "MT"),
    ("Jul 2023", "Persian Gulf",                     "Both"),
    ("Nov 2023", "Red Sea",                          "MT"),
    ("Feb 2024", "Mediterranean",                    "VT"),
    ("May 2024", "Northern Europe",                  "Both"),
    ("Sep 2024", "US East Coast",                    "MT"),
    ("Jan 2025", "Gulf of Mexico",                   "Both"),
    ("May 2025", "Panama",                           "MT"),
]

waypoints = []
unresolved = 0
for month, region, source in rows:
    hit = resolve_port(region)
    if hit is None:
        unresolved += 1
        print(f"[unresolved] {region}")
        continue
    port, lon, lat = hit
    waypoints.append(Waypoint(month=month, region=region, source=source,
                              port=port, lon=lon, lat=lat))

print(f"\nResolved {len(waypoints)} / {len(rows)} ({unresolved} unresolved)")

meta = render(waypoints, "smoke_long.png",
              title="Vessel route — Dec 2016 → May 2025 (9 năm)")
print(f"\nTotal {meta['total_nm']:.0f} nm across {len(meta['legs'])} legs")
