# The justice funnel: from arrest to outcome in New York City

An interactive explorer of what happens to criminal cases after the arrest — declined, dismissed, pled down, convicted, sentenced — by borough and charge type, and how it shifted since New York's bail laws changed on January 1, 2020.

Because no single public dataset follows one arrest from arrest to sentence, the tool presents two complementary views on two different clocks:

- **Outcomes of disposed cases** (DCJS disposition tables, 2014–2024) — cases reaching a final outcome each year. Spans the bail-reform line.
- **The arraignment cohort** (OCA pretrial case files, 2020–2024) — cases first arraigned each year, followed forward, including the release decision at arraignment.

## Files

- `build_dispositions.py` — parses DCJS county spreadsheets across three editions → `data/dispositions.json` (needs `xlrd`)
- `build_cohorts.py` — aggregates ~900k OCA case rows → `data/cohorts.json` (downloads raw CSVs from the Internet Archive on first run; standard library only)
- `build_arrests.py` — DCJS arrest counts for context → `data/arrests.json`
- `index.html` — the static site, with a self-contained SVG Sankey
- `METHODOLOGY.md` — sources, the two-clock design, category mapping, caveats

Local preview: `python3 -m http.server 8215` in this directory.

Raw OCA CSVs (~800 MB) are gitignored; only the derived JSON is committed.
