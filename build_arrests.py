#!/usr/bin/env python3
# Title: The justice funnel — arrest context pipeline
# Author: Josh Greenman with Claude Code
# Date: 2026-07-10
# Data source: DCJS "Adult Arrests 18 and Older by County: Beginning 1970"
#   (data.ny.gov, dataset rikd-mt35). Fingerprintable arrests by arrest year.
# Description: pulls NYC-county arrest counts (felony/misdemeanor/total) since
#   2014 for top-of-funnel context. NOT joined to dispositions — different
#   denominator and different clock; shown as context only.
# Dependencies: Python 3 standard library.

import json
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
NYC = {"New York": "Manhattan", "Kings": "Brooklyn", "Queens": "Queens",
       "Bronx": "The Bronx", "Richmond": "Staten Island"}
URL = "https://data.ny.gov/resource/rikd-mt35.json"


def main():
    q = urllib.parse.urlencode({"$where": "year >= 2014", "$limit": "50000"})
    rows = json.load(urllib.request.urlopen(URL + "?" + q, timeout=60))
    data = {}
    for r in rows:
        co = r["county"]
        if co not in NYC:
            continue
        y = int(r["year"])
        rec = data.setdefault(NYC[co], {}).setdefault(y, {"felony": 0, "misdemeanor": 0, "total": 0})
        rec["felony"] += int(float(r.get("felony_total", 0)))
        rec["misdemeanor"] += int(float(r.get("misdemeanor_total", 0)))
        rec["total"] += int(float(r.get("total", 0)))
    city = {}
    for ys in data.values():
        for y, rec in ys.items():
            c = city.setdefault(y, {"felony": 0, "misdemeanor": 0, "total": 0})
            for k in c:
                c[k] += rec[k]
    data["New York City"] = city
    out = {
        "meta": {
            "built": "2026-07-10",
            "source": "DCJS Adult Arrests 18 and Older by County (rikd-mt35), data.ny.gov",
            "basis": "fingerprintable arrests by arrest year",
            "note": "Arrest counts (arrest year) and dispositions (disposition year) are different denominators; shown as context, not a literal flow.",
        },
        "data": data,
    }
    (HERE / "data" / "arrests.json").write_text(json.dumps(out, separators=(",", ":")))
    print("Wrote data/arrests.json; NYC 2024:", city[2024])


if __name__ == "__main__":
    main()
