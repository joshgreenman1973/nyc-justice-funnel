#!/usr/bin/env python3
# Title: The justice funnel — OCA arraignment-cohort pipeline (View B)
# Author: Josh Greenman with Claude Code
# Date: 2026-07-10
# Data source:
#   New York State Office of Court Administration, Pretrial Release Data
#   (https://ww2.nycourts.gov/pretrial-release-data-33136), case-level CSVs
#   by arraignment year, published under the 2019 bail reform legislation.
#   Files used: "NYS for Web 2020..2024.csv".
#   - 2020 and 2024 files: Wayback Machine snapshot of December 2025
#   - 2021-2023 files: Wayback Machine snapshots of March 2025
#   (nycourts.gov blocks automated downloads; the Wayback Machine mirrors
#   the exact published files. Snapshot vintage per file is recorded in meta.)
# Description: aggregates ~900k case rows into a funnel per
#   (cohort year, borough, arrest-charge severity):
#     arraigned -> release decision at arraignment -> case outcome
#     -> conviction charge severity -> most severe sentence,
#   following felony cases transferred to superior court via arr_cycle_id
#   so a transferred case is counted once, with its superior-court outcome.
# Dependencies: Python 3 standard library (csv, json).

import csv
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

# nycourts.gov blocks automated clients (Cloudflare), so the case files are
# pulled from the Internet Archive's mirror of the exact published CSVs.
# Each entry: (wayback timestamp, snapshot label shown in methodology).
WB = {
    2020: ("20251220000000", "2025-12"),
    2021: ("20250306141625", "2025-03"),
    2022: ("20250307191419", "2025-03"),
    2023: ("20250306085704", "2025-03"),
    2024: ("20251220000000", "2025-12"),
}
COURT_URL = "https://www.nycourts.gov/legacypdfs/court-research/NYS%20for%20Web%20{y}.csv"
SNAPSHOTS = {y: lbl for y, (_, lbl) in WB.items()}


def ensure_file(year):
    """Return a local path to year's OCA CSV, downloading from Wayback if absent."""
    dest = RAW / f"nys{year}_full.csv"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    ts, _ = WB[year]
    url = f"http://web.archive.org/web/{ts}id_/" + COURT_URL.format(y=year)
    print(f"  downloading {year} from Internet Archive...")
    req = urllib.request.Request(url, headers={"User-Agent": "justice-funnel research"})
    with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    print(f"  saved {dest.name} ({dest.stat().st_size:,} bytes)")
    return dest


FILES = {y: ensure_file(y) for y in WB}

NYC = {"New York": "Manhattan", "Kings": "Brooklyn", "Queens": "Queens",
       "Bronx": "The Bronx", "Richmond": "Staten Island"}

REL = {"Disposed at arraign": "disposed_arraign", "ROR": "ror",
       "Nonmonetary release": "nmr", "Remanded": "remand", "Unknown": "rel_unknown"}

SENT = {"Imprisonment-Not Time Served": "incarceration", "Imprisonment Time Served": "time_served",
        "Probation": "probation", "Fine": "fine", "Conditional Discharge": "cond_discharge",
        "Surcharge": "sent_other", "Fee": "sent_other", "Restitution": "sent_other",
        "License": "sent_other", "Unconditional Discharge": "sent_other"}


def yes(v):
    return (v or "").strip().upper() in ("Y", "YES", "1", "TRUE")


def release_bucket(r):
    d = (r["Release Decision at Arraign"] or "").strip()
    if d == "Bail-set":
        return "bail_posted" if yes(r["Bail_Set_and_Posted_at_Arraign"]) else "bail_not_posted"
    return REL.get(d, "rel_unknown")


def outcome_bucket(dispo, docket):
    dispo = (dispo or "").strip()
    if dispo == "Plea":
        return "plea"
    if dispo == "Verdict-TFG":
        return "trial_guilty"
    if dispo == "Verdict-ACQ":
        return "acquitted"
    if dispo == "Dismissed":
        return "dismissed"
    if dispo == "Dism-ACD":
        return "acd"
    if dispo == "Other":
        return "outcome_other"
    if dispo == "":
        return "pending"  # includes Tolled/Open Warrant
    return None  # GJ/Trans handled by caller


def conv_bucket(sev):
    sev = (sev or "").strip()
    if sev == "Felony":
        return "conv_felony"
    if sev == "Misdemeanor":
        return "conv_misd"
    if sev in ("Violation", "Infraction"):
        return "conv_noncrim"
    return "conv_unknown"


def sent_bucket(s):
    s = (s or "").strip()
    if not s:
        return "sent_none"
    return SENT.get(s, "sent_other")


def main():
    # Pass 1: superior-court rows across all files, keyed by arr_cycle_id.
    # Used to resolve the outcome of local cases transferred by grand jury.
    superior = {}
    sup_count = 0
    for year, path in FILES.items():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if (r["Court_Type"] or "").strip() != "Superior":
                    continue
                sup_count += 1
                cyc = (r["arr_cycle_id"] or "").strip()
                if not cyc:
                    continue
                cur = superior.get(cyc)
                # prefer a row with a real disposition over a pending one
                if cur is None or (not cur["dispo"] and (r["Disposition_Type"] or "").strip()):
                    superior[cyc] = {
                        "dispo": (r["Disposition_Type"] or "").strip(),
                        "docket": (r["Docket_Status"] or "").strip(),
                        "conv_sev": (r["Top_Charge_Severity_at_Conviction"] or "").strip(),
                        "sentence": (r["Most_Severe_Sentence"] or "").strip(),
                    }
        print(f"  superior pass {year} done")

    # Pass 2: local-court NYC rows = the cohort base.
    # agg[(year, borough, sev)] = nested counters
    agg = defaultdict(lambda: {
        "n": 0,
        "release": defaultdict(int),
        "rel_out": defaultdict(int),      # (release, outcome) joint
        "out_conv": defaultdict(int),     # (outcome, conv severity) joint, convictions only
        "conv_sent": defaultdict(int),    # (conv severity, sentence) joint
        "transfer_resolved": 0,
        "transfer_unresolved": 0,
    })
    used_severities = ("Felony", "Misdemeanor")
    for year, path in FILES.items():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if (r["Court_Type"] or "").strip() != "Local":
                    continue
                county = (r["County_Name"] or "").strip()
                if county not in NYC:
                    continue
                sev = (r["Top_Charge_Severity_at_Arrest"] or "").strip()
                sev = sev if sev in used_severities else "Other"
                rel = release_bucket(r)
                dispo = (r["Disposition_Type"] or "").strip()

                if dispo == "GJ/Trans":
                    cyc = (r["arr_cycle_id"] or "").strip()
                    sup = superior.get(cyc)
                    if sup and sup["dispo"]:
                        out = outcome_bucket(sup["dispo"], sup["docket"]) or "pending"
                        conv_sev, sentence = sup["conv_sev"], sup["sentence"]
                        resolved = True
                    elif sup:
                        out, conv_sev, sentence, resolved = "pending", "", "", True
                    else:
                        out, conv_sev, sentence, resolved = "transfer_unknown", "", "", False
                else:
                    out = outcome_bucket(dispo, (r["Docket_Status"] or "").strip()) or "pending"
                    conv_sev, sentence = (r["Top_Charge_Severity_at_Conviction"] or "").strip(), (r["Most_Severe_Sentence"] or "").strip()
                    resolved = None

                for combo in [(year, NYC[county], sev), (year, "New York City", sev),
                              (year, NYC[county], "All"), (year, "New York City", "All")]:
                    a = agg[combo]
                    a["n"] += 1
                    a["release"][rel] += 1
                    a["rel_out"][rel + "|" + out] += 1
                    if out in ("plea", "trial_guilty"):
                        cb = conv_bucket(conv_sev)
                        a["out_conv"][out + "|" + cb] += 1
                        a["conv_sent"][cb + "|" + sent_bucket(sentence)] += 1
                    if resolved is True:
                        a["transfer_resolved"] += 1
                    elif resolved is False:
                        a["transfer_unresolved"] += 1
        print(f"  local pass {year} done")

    out = {
        "meta": {
            "built": "2026-07-10",
            "basis": "cases first arraigned in the given year (arraignment cohorts), followed to disposition as of the source snapshot",
            "source": "NYS Office of Court Administration, Pretrial Release Data",
            "snapshots": SNAPSHOTS,
            "superior_rows_indexed": sup_count,
            "notes": [
                "Local-court NYC arraignments only form the cohort base; superior-court cases without a linked local arraignment (e.g. courts not yet on the UCMS system) are not included.",
                "Felony cases transferred to a grand jury / superior court are followed via arr_cycle_id and counted once with their superior-court outcome.",
                "Pending includes tolled dockets and open warrants.",
            ],
        },
        "cohorts": {
            f"{y}|{b}|{s}": {
                "n": a["n"],
                "release": dict(a["release"]),
                "rel_out": dict(a["rel_out"]),
                "out_conv": dict(a["out_conv"]),
                "conv_sent": dict(a["conv_sent"]),
                "transfer_resolved": a["transfer_resolved"],
                "transfer_unresolved": a["transfer_unresolved"],
            }
            for (y, b, s), a in sorted(agg.items())
        },
    }
    dest = HERE / "data" / "cohorts.json"
    dest.write_text(json.dumps(out, separators=(",", ":")))
    print(f"\nWrote {dest} ({dest.stat().st_size:,} bytes, {len(out['cohorts'])} combos)")
    # headline check
    k = "2024|New York City|All"
    a = out["cohorts"][k]
    print(k, "n =", a["n"])


if __name__ == "__main__":
    sys.exit(main())
