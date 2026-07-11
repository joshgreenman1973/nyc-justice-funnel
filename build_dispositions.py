#!/usr/bin/env python3
# Title: The justice funnel — DCJS dispositions pipeline (View A)
# Author: Josh Greenman with Claude Code
# Date: 2026-07-10
# Data sources:
#   New York State Division of Criminal Justice Services (DCJS),
#   "Dispositions of Adult Arrests (18 and Older)" county spreadsheets:
#   https://www.criminaljustice.ny.gov/crimnet/ojsa/dispos/index.htm
#   - Current edition: disposition years 2020-2024 (accessed 2026-07-10)
#   - June 2022 edition via Wayback Machine: disposition years 2017-2021
#     (we use 2017-2019 from it)
#   - February 2020 edition via Wayback Machine: disposition years 2014-2018
#     (we use 2014-2016 from it)
# Description: parses the felony and misdemeanor blocks of each borough's
#   spreadsheet in each edition, maps category labels across editions to a
#   canonical vocabulary, and writes data/dispositions.json.
#   Counts are of arrests REACHING FINAL DISPOSITION in the given year
#   (disposition-year basis, not arrest cohorts) — see DCJS data notes:
#   https://www.criminaljustice.ny.gov/crimnet/ojsa/dispos/dispositiondatanotes.pdf
# Dependencies: Python 3, xlrd 2.x (legacy .xls reader).

import json
import re
import sys
import urllib.request
from pathlib import Path

import xlrd

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

BOROUGHS = {
    "bronx": "The Bronx",
    "kings": "Brooklyn",
    "newyork": "Manhattan",
    "queens": "Queens",
    "richmond": "Staten Island",
}

# Editions, newest first. Each: (tag, base URL or wayback prefix, years to take)
CURRENT_BASE = "https://www.criminaljustice.ny.gov/crimnet/ojsa/dispos/{b}.xls"
WB2022 = "http://web.archive.org/web/20220608023009id_/https://www.criminaljustice.ny.gov/crimnet/ojsa/dispos/{b}.xls"
WB2020 = "http://web.archive.org/web/20200218202909id_/https://www.criminaljustice.ny.gov/crimnet/ojsa/dispos/{b}.xls"
EDITIONS = [
    ("current", CURRENT_BASE, {2020, 2021, 2022, 2023, 2024}),
    ("ed2022", WB2022, {2017, 2018, 2019}),
    ("ed2020", WB2020, {2014, 2015, 2016}),
]

# Canonical outcome categories <- label prefixes as they appear across editions
OUTCOMES = {
    "DA Declined to Prosecute": "declined",
    "Dismissed-Not ACD": "dismissed",
    "Dismissed-ACD": "acd",
    "Diverted and Dismissed": "diverted",
    "Acquitted": "acquitted",
    "Other Favorable": "other",   # current edition
    "Other": "other",             # 2014-2018 edition ("cases abandoned...")
    "Covered by Another Case": "covered",
    "Convicted-Sentenced": "convicted",
    "Total Dispositions": "total",
}
CONVICTIONS = {"Felonies": "conv_felony", "Misdemeanors": "conv_misd",
               "Non-Criminal": "conv_noncrim", "Non-Criminal/Unknown": "conv_noncrim",
               "Unknown": "conv_noncrim"}
SENTENCES = {"Prison": "prison", "Jail": "jail", "Time Served": "time_served",
             "Jail + Probation": "jail_probation", "Jail+Probation": "jail_probation",
             "Probation": "probation", "Fine": "fine", "Cond Discharge": "cond_discharge",
             "Other": "sent_other", "Other/Unknown": "sent_other"}


def fetch(url, dest):
    if dest.exists() and dest.stat().st_size > 10000:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (justice-funnel research)"})
    data = urllib.request.urlopen(req, timeout=180).read()
    dest.write_bytes(data)
    print(f"  downloaded {dest.name} ({len(data):,} bytes)")
    return dest


def parse_sheet(path):
    """Return {year: {severity: {canonical_key: count}}} for Felony/Misdemeanor blocks."""
    wb = xlrd.open_workbook(path)
    # data sheet = the one whose row 3-ish mentions "Top Arrest Charge"
    sheet = None
    for name in wb.sheet_names():
        sh = wb.sheet_by_name(name)
        head = " ".join(str(sh.cell_value(r, 0)) for r in range(min(6, sh.nrows)))
        if "COUNTY" in head.upper() or "Top Arrest Charge" in head:
            sheet = sh
            break
    if sheet is None:
        raise ValueError(f"No data sheet in {path}")

    # Year columns: the row where col 3 is a 4-digit year. N columns follow at 3,5,7,9,11.
    years, ycols = [], []
    for r in range(min(8, sheet.nrows)):
        for c in range(3, sheet.ncols, 2):
            v = sheet.cell_value(r, c)
            if isinstance(v, str):
                v = float(v) if re.fullmatch(r"\d{4}", v.strip()) else 0
            if isinstance(v, float) and 2000 < v < 2100:
                years.append(int(v))
                ycols.append(c)
        if years:
            break
    if not years:
        raise ValueError(f"No year header in {path}")

    out = {y: {} for y in years}
    severity = None       # current block: Felony / Misdemeanor / (skipped subsets)
    section = "outcome"   # outcome | convictions | sentences | yo
    for r in range(sheet.nrows):
        c0 = str(sheet.cell_value(r, 0)).strip()
        c1 = str(sheet.cell_value(r, 1)).strip()
        c2 = str(sheet.cell_value(r, 2)).strip()
        if c0:
            severity = c0 if c0 in ("Felony", "Misdemeanor") else None
            section = "outcome"
        if severity is None:
            continue
        if c1.startswith("Adult Non-YO Convictions") or c1 == "Convictions for:":
            section = "convictions"
        elif c1.startswith("Youthful Offender"):
            section = "yo"
        elif c1 == "Sentences to:":
            section = "sentences"

        label = c2 if c2 else c1
        # strip the "Convictions for:"/"Sentences to:" prefix rows carry their first item in c2
        key = None
        if section == "outcome" and c1 and not c2:
            key = OUTCOMES.get(c1)
        elif section in ("convictions", "yo") and c2:
            k = CONVICTIONS.get(c2)
            key = k  # YO adjudications are added into the same conviction buckets
        elif section == "sentences" and c2:
            key = SENTENCES.get(c2)
        if not key:
            continue
        for y, c in zip(years, ycols):
            v = sheet.cell_value(r, c)
            if isinstance(v, str):
                try:
                    v = float(v.strip().replace(",", ""))
                except ValueError:
                    v = 0.0
            n = int(v) if isinstance(v, float) else 0
            sev = out[y].setdefault(severity, {})
            sev[key] = sev.get(key, 0) + n
    return out


def main():
    data = {}   # borough -> year -> severity -> {key: n}
    sourcing = {}  # year -> edition tag (for methodology display)
    for tag, base, want_years in EDITIONS:
        print(f"Edition {tag}:")
        for slug, borough in BOROUGHS.items():
            # 2022 wayback snapshot capitalized filenames; try both
            names = [slug, slug.capitalize(), slug.title()]
            path = None
            for nm in names:
                try:
                    path = fetch(base.format(b=nm), RAW / f"{tag}_{slug}.xls")
                    break
                except Exception as e:
                    err = e
                    continue
            if path is None:
                print(f"  FAILED {slug}: {err}", file=sys.stderr)
                sys.exit(1)
            parsed = parse_sheet(path)
            for y, sevs in parsed.items():
                if y not in want_years:
                    continue
                sourcing[y] = tag
                for sev, kv in sevs.items():
                    data.setdefault(borough, {}).setdefault(y, {}).setdefault(sev, {})
                    for k, n in kv.items():
                        data[borough][y][sev][k] = n

    # Citywide = sum of the five boroughs
    city = {}
    for borough, ys in data.items():
        for y, sevs in ys.items():
            for sev, kv in sevs.items():
                tgt = city.setdefault(y, {}).setdefault(sev, {})
                for k, n in kv.items():
                    tgt[k] = tgt.get(k, 0) + n
    data["New York City"] = city

    # Sanity checks: components should sum ~ total (YO/unknown rounding aside)
    problems = []
    for borough, ys in data.items():
        for y, sevs in ys.items():
            for sev, kv in sevs.items():
                total = kv.get("total", 0)
                parts = sum(kv.get(k, 0) for k in
                            ("declined", "dismissed", "acd", "diverted", "acquitted",
                             "other", "covered", "convicted"))
                if total and abs(parts - total) > total * 0.01:
                    problems.append(f"{borough} {y} {sev}: parts {parts} vs total {total}")
                conv = kv.get("convicted", 0)
                csum = sum(kv.get(k, 0) for k in ("conv_felony", "conv_misd", "conv_noncrim"))
                if conv and abs(csum - conv) > max(10, conv * 0.02):
                    problems.append(f"{borough} {y} {sev}: convictions {csum} vs convicted {conv}")
    if problems:
        print("SANITY WARNINGS:")
        for p in problems:
            print("  " + p)

    out = {
        "meta": {
            "built": "2026-07-10",
            "basis": "disposition year (cases reaching final disposition that year), not arrest cohorts",
            "source": "DCJS Dispositions of Adult Arrests (18 and Older), county spreadsheets",
            "editions": {
                "current": "criminaljustice.ny.gov, accessed 2026-07-10 (years 2020-2024; file dated May 2025)",
                "ed2022": "Wayback Machine snapshot 2022-06-08 (years 2017-2019)",
                "ed2020": "Wayback Machine snapshot 2020-02-18 (years 2014-2016)",
            },
            "year_sourcing": {str(y): t for y, t in sorted(sourcing.items())},
        },
        "data": data,
    }
    (HERE / "data" / "dispositions.json").write_text(json.dumps(out, separators=(",", ":")))
    yrs = sorted(sourcing)
    print(f"\nWrote data/dispositions.json: {len(data)} geographies, years {yrs[0]}-{yrs[-1]}")


if __name__ == "__main__":
    main()
