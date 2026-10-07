"""Smoke test: render the sample voyage without launching Streamlit."""
from route import Waypoint, render
from ports import resolve_port

rows = [
    ("Dec 2016", "Australia / New Guinea Pacific",  "MarineTraffic"),
    ("Jan 2017", "East Asia / SE Asia / Australia", "Both"),
    ("Feb 2017", "East Asia / SE Asia",             "Both"),
    ("Mar 2017", "East Asia / SE Asia",             "VesselTracker"),
    ("Apr 2017", "East Asia -> NA West Coast",      "MarineTraffic"),
    ("May 2017", "North America West Coast",        "Both"),
    ("Jun 2017", "North America West Coast",        "Both"),
    ("Jul 2017", "Gulf of Mexico / Middle America", "MarineTraffic"),
]

# Override Mar 2017 -> Ningbo to match the original context
overrides = {"Mar 2017": "Ningbo-Zhoushan"}

from ports import PORTS

waypoints = []
for month, region, source in rows:
    port, lon, lat = resolve_port(region)
    if month in overrides:
        port = overrides[month]
        lon, lat = PORTS[port]
    waypoints.append(Waypoint(month=month, region=region, source=source,
                              port=port, lon=lon, lat=lat))

meta = render(waypoints, "smoke_output.png",
              title="Vessel route — Dec 2016 → Jul 2017")
print(f"OK — total {meta['total_nm']:.0f} nm across {len(meta['legs'])} legs")
for leg in meta["legs"]:
    print(f"  {leg['from']:>22}  ->  {leg['to']:<22}  {leg['distance_nm']:>8.0f} nm")
