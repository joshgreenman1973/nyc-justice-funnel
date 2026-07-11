# The justice funnel — methodology

Last updated: 2026-07-10

## What this is

An interactive explorer of what happens to criminal cases in New York City after the arrest: how many are declined by prosecutors, dismissed, pled down, convicted and sentenced — by borough, by charge type, over time. Because no single public dataset follows one arrest from arrest to sentence, the tool presents **two complementary views** built from two different official sources on two different clocks.

## The two views

### View A — "Outcomes of disposed cases" (2014–2024)

**Source:** New York State Division of Criminal Justice Services (DCJS), [Dispositions of Adult Arrests (18 and Older)](https://www.criminaljustice.ny.gov/crimnet/ojsa/dispos/index.htm), the county-level spreadsheets.

Every adult arrest that reached a **final disposition** in a given year, and what that disposition was, split by felony vs misdemeanor top arrest charge. This is the view that spans the bail-reform line.

**Critical semantics (from the DCJS [data notes](https://www.criminaljustice.ny.gov/crimnet/ojsa/dispos/dispositiondatanotes.pdf)):**
- Counts are by **disposition year, not arrest year** — "an arrest from 2018 that was disposed in 2019 would be displayed in 2019." A funnel for year X is *cases that ended in X*, not *arrests made in X*.
- Only fully disposed arrests appear; cases still open, with interim dispositions, or convicted-but-not-yet-sentenced are excluded from the denominator.
- Outcomes are categorized by the **most serious charge at arrest**.
- The conviction charge is recorded separately, so a felony arrest ending in a misdemeanor or non-criminal conviction (a "plea down") is visible.
- "DA Declined to Prosecute" "primarily occurs in the five counties/boroughs of New York City."

**Editions and how we assembled 2014–2024.** DCJS publishes a rolling five-year window. We combined three editions, taking each year from exactly one edition:
- **2020–2024** from the current edition (criminaljustice.ny.gov, file dated May 2025, accessed 2026-07-10).
- **2017–2019** from the June 2022 edition via the Internet Archive.
- **2014–2016** from the February 2020 edition via the Internet Archive.

Category labels differ slightly across editions (e.g. the 2014–2018 edition splits convictions into "Adult Non-YO" and "Youthful Offender" adjudications, which we sum into the same felony/misdemeanor/non-criminal conviction buckets; it labels "Other Favorable" simply "Other"). The parser (`build_dispositions.py`) maps every edition's labels to one canonical vocabulary and runs internal sanity checks that outcome components sum to the disposition total and conviction levels sum to the convicted total. Overlapping years across editions differ slightly because DCJS receives late disposition reports; we never mix editions within a year.

### View B — "The arraignment cohort" (2020–2024)

**Source:** New York State Office of Court Administration, [Pretrial Release Data](https://ww2.nycourts.gov/pretrial-release-data-33136), the case-level CSVs published under the 2019 bail-reform legislation, one file per arraignment year.

Every case **first arraigned** in a given year, followed forward to its disposition as of the data's publication. This is the only view that shows what happened at arraignment — released on recognizance, nonmonetary conditions, bail set (and whether it was posted), or remand — the machinery bail reform actually changed.

**How the funnel is built (`build_cohorts.py`):**
- The cohort base is **local-court New York City arraignments** (the five boroughs). Superior-court cases that have no linked local arraignment (for example, courts not yet migrated to the unified case-management system as of the file's `UCMSLiveDate`) are not part of the base and may be incomplete.
- **Felony cases sent to a grand jury / superior court** appear in the local file as a "GJ/Trans" disposition and again as a separate superior-court row. We link the two by the case identifier (`arr_cycle_id`) and count the local case **once**, carrying its superior-court outcome, conviction level and sentence forward. Where the superior-court record can't be found (arraigned later, or not yet on the system), the case is shown as "sent to grand jury (outcome not in data)" rather than silently dropped.
- **Transfer-attribution uncertainty.** About 15% of transferred felony cycles map to more than one superior-court docket, whose outcomes can differ (a single arrest cycle can carry multiple dockets). We attribute the first disposed superior outcome to the local case. Testing alternative rules (prefer a conviction, prefer a dismissal) moves the felony conviction rate by up to ~2 percentage points. This affects only the felony outcome column of View B; the release stage, the case counts and every figure in View A are unaffected.
- Release, outcome, conviction level and sentence are taken from the file's own fields; the release→outcome ribbons use the joint distribution, not independent marginals.

**Caveats:**
- **No pre-reform baseline** — the data starts with 2020 arraignments.
- **Right-censoring** — recent cohorts are incomplete. A large share of 2024 felony cases were still pending when the data was published; they are shown as "pending," not as favorable outcomes. The tool defaults to 2022, a more complete cohort, and flags high pending shares in the subtitle.
- **Snapshots:** files pulled from the Internet Archive's mirror of nycourts.gov (which blocks automated download). 2020 and 2024 from the December 2025 snapshot; 2021–2023 from March 2025 snapshots. Later cohorts will keep filling in as the courts republish.

## Arrest context

The top-of-funnel arrest counts (DCJS [Adult Arrests by County](https://data.ny.gov/resource/rikd-mt35.json), dataset `rikd-mt35`) are shown for context only. **Arrest counts and disposition counts are different denominators on different clocks** — arrests are fingerprintable arrests by arrest year; dispositions are cases ending by disposition year — so the tool never draws a literal flow from the arrest bar into the disposition funnel.

## Domain notes and shared caveats

These are the things a criminal-justice reader should hold in mind.

- **Unit of counting.** View A (DCJS) counts **arrest events**: one fingerprintable arrest is one record, categorized by its most serious charge, "and for arrest events with multiple charges, the disposition shown is the most serious disposition" (DCJS data notes). View B (OCA) counts **court dockets**, and one arrest can generate more than one docket. Neither counts unique individuals — a person arrested three times appears three times.
- **"Convicted" means convicted *and sentenced*.** DCJS: "a conviction without a sentence [is] not considered fully disposed and [is] not displayed." Convictions awaiting sentencing sit outside both the numerator and the denominator, so the conviction rate is measured among fully disposed arrests.
- **The conviction-rate denominator includes declined and dismissed cases.** This tool reports convictions as a share of *all disposed arrests*, not of *prosecuted* cases. That is why its conviction rate reads lower than analyses that divide convictions by cases actually prosecuted — a different, equally valid construct. Every headline states its denominator.
- **January 2020 changed several things at once.** Bail reform, the new discovery law (Criminal Procedure Law Article 245) and speedy-trial rules all took effect January 1, 2020; the discovery law's hard evidence-disclosure deadlines are widely credited as a larger driver of the post-2020 rise in dismissals than bail reform itself. COVID closed the courts weeks later. The tool labels the 2020 line as "2020 reforms / COVID" rather than attributing the shift to bail reform alone. DCJS warns against treating 2020 as a normal year; for a cleaner contrast compare 2019 with 2021+. None of these reforms is a single event (bail was amended in 2020, 2022, 2023; discovery in 2025).
- **"Custodial sentence" includes time served.** A large share of custodial sentences (often the majority, for misdemeanors) is "time served" — the sentence equals pretrial detention already served, after which the person is released. The sentence panel separates prison, jail and time served; the summary callout states the time-served share.
- **Declined-to-prosecute is undercounted and NYC-specific.** DCJS: this disposition "primarily occurs in the five counties/boroughs of New York City." It captures declinations at or after arraignment; cases a DA declines *before* arraignment never enter the data.
- **Youthful Offender adjudications count as convictions.** For the 18-year-olds in this adult dataset, YO status (under 1% of cases, per DCJS) is folded into the conviction categories, consistent with DCJS's own tables.
- **Diversion is undercounted.** DCJS: "Not all 'Diverted and dismissed' dispositions are reported to DCJS," so treatment-court and diversion outcomes are understated.
- **ACD is a conditional dismissal.** "Dismissed (ACD)" (CPL 170.55) is an adjournment in contemplation of dismissal — the case is dismissed later if the defendant stays out of trouble. It is shown as its own node and grouped with dismissals, never with convictions.
- **Small slices:** Staten Island felony counts in some years are small; percentages there are noisier.

## Reproducing this

```
python3 build_dispositions.py   # -> data/dispositions.json  (needs xlrd)
python3 build_cohorts.py        # -> data/cohorts.json  (downloads ~800MB of OCA CSVs from the Internet Archive on first run; cached in data/raw, which is gitignored)
python3 build_arrests.py        # -> data/arrests.json  (or the inline Socrata fetch; standard library only)
```

The site (`index.html`) is static and reads the three JSON files. Raw OCA CSVs are not committed (too large); the derived `cohorts.json` is ~190 KB. Spot-checks against the source spreadsheets (e.g. Brooklyn felony 2024: 25,295 dispositions, 1,639 declined, 6,201 convicted, 964 prison sentences) match cell-for-cell.
