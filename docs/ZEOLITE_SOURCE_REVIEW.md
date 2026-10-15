# P100-026 — silver-zeolite reactor reconstruction

This is a private reconstruction draft, not a new admitted scenario or a new experiment. The historical edition, private evaluator targets, frozen runtime and all existing outcomes remain unchanged.

## Source and scientific meaning

The registry identifies [Zenodo record 15691695](https://zenodo.org/records/15691695), DOI `10.5281/zenodo.15691695`, for the publication *Non-oxidative dehydrogenation of methanol to dimethoxymethane over Ag/Hβ zeolite bifunctional catalyst* (DOI `10.1039/d5cy00544b`). The stored record describes continuous gas-phase fixed-bed experiments and declares CC BY 4.0. It lists Palkovits, Simitsis, Mebrahtu, Müller and Zobel. Final redistribution, attribution and scientific-contract approval remain pending; the original acquisition is not bundled into an upload root.

The task forecasts author-reported dimethoxymethane (DMM) selectivity from an already observed reactor prefix. It does not reconstruct chromatograms, establish a reaction mechanism or predict an unmeasured catalyst. Ag loading comes from source run labels; physical catalyst-batch independence and acquisition dates have not been established. Temperature-labelled and calcined runs are held out, but temperature and treatment are not new predictors introduced by this reconstruction.

## Native measurements and permitted calibration

The original 7z archive contains 459 entries and expands to 102,695,483 bytes. Only nine registered reaction tables, totaling 247,897 bytes, are decoded to memory. The exact bsdtar/libarchive executable and version are bound in the recipe. Member count, expanded sizes, types, safe paths, selected names, lengths and hashes are checked. Extraction has output/time limits, writes no archive members to disk and does not execute source code.

Each table has three header rows and eight tab-separated columns. Column A is time on stream in minutes; column G is DMM selectivity in percent. Other selectivities, instantaneous conversion, activity and literal formulas are excluded from predictors and are never evaluated. Missing source responses remain explicit source-row exclusions.

For each complete run, the task uses:

- The last finite response at or before 300 minutes as its selectivity anchor.
- Elapsed time relative to that anchor.
- An analytical OLS slope from finite responses in the fixed 120–300 minute window: `sum((t-mean(t))*(y-mean(y)))/sum((t-mean(t))**2)`.
- Source-labelled Ag loading of 1, 5 or 20 weight percent.

These are **eight analytical prefix calibrations**, each with a slope/intercept calculation, not zero fitted preprocessing. They are recorded separately from zero discovery-rule fitting attempts. The test runs receive the same permitted prefix calibration. No scored response after 300 minutes feeds a predictor. Each retained target has `300 < time <= 1500` minutes. Missing values are not interpolated, filled or used to alter the cohort. A zero-clock restart would receive separate calibration within the same run and split; the actual eight runs contain no restarts.

## Identity, missingness and splits

`Figure1_longterm-reaction_Ag20-Hbeta` and `FigureS14b_reaction_Ag20-Hbeta-red` contain the same time/DMM measurements and missing-response positions. Their fixed alias is checked and the observations counted once. Other exported formulas differ slightly; formula text is not used to create a new run identity.

The eight distinct runs contain 2,061 source rows, of which 1,672 have finite DMM responses and 389 are explicitly missing. The missing rows comprise 90 in Ag1, 295 in Ag5, two in the S12c/S13a Ag20 run and two in the reduced long-term run. All 862 eligible task rows are preserved.

| Partition | Whole runs | Task rows | Definition |
|---|---:|---:|---|
| Train | 4 | 389 | Ag1, Ag5, S12c/S13a Ag20 and reduced long-term Ag20 |
| Dev | 2 | 240 | T240- and T280-labelled runs; original compact-v2 hash allocation |
| Test | 2 | 233 | T220-labelled and calcined runs; original confirmation allocation |

The inherited observation prose mentions the earlier six-run leave-run-out development protocol. The compact release itself uses the fixed four/two/two allocation above; do not describe its fitting procedure as six-fold validation. Whole-file separation does not prove independent catalyst batches, instruments or acquisition sessions.

## Verification and limits

[The installed-wheel receipt](NATIVE_ZEOLITE_VERIFICATION.json) verifies all 862 sample identities and groups, unchanged partition membership and **zero numerical differences** against public development measurements and permitted test inputs. It never opens the evaluator vault. All eight generated artifacts replay byte-for-byte using the separately installed wheel. The private draft occupies **397,989 expanded bytes** (314,448 stored), including recipe, lineage and reconstruction records; the large source archive stays outside it.

Thirty synthetic tests cover causal calibration, later-response and other-channel independence, complete-run grouping across restarts, missing-row coordinates, fixed duplicate identity, units/domain guards, changed source hashes and unsafe archive entries. The full suite has 495 passing tests. A read-only [browser check](ZEOLITE_UI_VERIFICATION.json) verifies scenario selection, all 13 assigned attempt rows, 18 rules and the Engine Rule Card. One Qwen attempt remains failed because its response was truncated; three assessed rules remain below the accuracy gate. Neither is hidden or rerun.

The draft still requires source-processing and physical-replication review, final rights/attribution packaging, contract approval and a justified perturbation model. Novelty, mechanism, practical impact and independent validation remain unassessed. No new comparison or model request was made.
