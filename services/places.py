"""Address lookup, to put a store on the map.

The admin uses it for a partner store added by hand (one without a POS, whose
coordinates Square would otherwise send): type the address, pick the match, and
the coordinates are saved with the store. OpenStreetMap's Nominatim, as
scripts/geocode_dispensaries.py uses for dispensaries; its usage policy asks for
an identifying User-Agent and at most one request a second, which a person
typing addresses one at a time stays under.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "terpenomics-geocode/1.0 (jambola441@gmail.com)"
TIMEOUT_SECONDS = 10


class LookupFailed(Exception):
    pass


def search(address: str, limit: int = 5) -> list[dict]:
    """[{"label", "lat", "lng"}], best match first; [] when nothing matches."""
    qs = urllib.parse.urlencode({"q": address, "format": "json", "limit": limit, "countrycodes": "us"})
    req = urllib.request.Request(f"{NOMINATIM}?{qs}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as r:
            rows = json.loads(r.read())
    except Exception as e:  # noqa: BLE001 — the lookup service's problem, said plainly
        raise LookupFailed(f"Address lookup failed: {e}") from e
    return [{"label": row.get("display_name") or address, "lat": float(row["lat"]), "lng": float(row["lon"])}
            for row in rows if row.get("lat") and row.get("lon")]
