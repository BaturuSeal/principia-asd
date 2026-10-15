# Calibrated kinase and neuronal response reconstruction

The P100-074 and P100-076 curator recipes reconstruct the historical prediction tables directly from hash-registered source CSV measurements. This review adds executable preparation, calibration lineage and source-identity checks. It does not fit a model, access the evaluator vault, change the frozen edition or establish independent test evidence. Original acquisitions already contain the retrospective responses and must remain outside discovery-worker access.

## P100-074: Src kinase fluorescence curves

The selected source is `Fig_S3A.csv` from the locally retained Zenodo record 18911385. Its nine labelled dose columns span 0.25–20 uM. The CSV explicitly labels time in minutes and dose in uM. Fluorescence response units and assay interpretation still require protocol-level review; these are published source values, not independently decoded optical acquisitions. Existing metadata records CC BY 4.0, with final redistribution and notice review pending.

Each dose has 54 observed responses at 0–39.75 minutes. Forecasting uses all 43 finite responses strictly after 7.5 minutes. The only permitted response-derived inputs are the same curve's observations at 3, 4.5 and 6 minutes:

- `calibration_F6 = F(6)`;
- `calibration_v6 = (F(6) - F(4.5)) / 1.5`;
- `calibration_curvature = (F(6) - 2 F(4.5) + F(3)) / 2.25`.

These are expanded finite differences, not fitted parameters. Their source rows, columns, times and units remain explicit. Every calibration precedes the forecast cohort. Negative baseline-corrected source values are preserved; no value-based outlier removal is applied.

The literal `--` marks unavailable data. Rows 56–123 have neither time nor responses; row 124 gives 91.5 minutes without any measured responses. Both forms of missingness remain in the reconstruction record. Observed responses without a time coordinate are rejected. Empty trailing source columns are excluded, and neither source padding nor unavailable values become fabricated measurements.

The complete **387-row** cohort reproduces with zero numerical differences: **215 train / 86 dev / 86 test-input rows**, with **5 / 2 / 2 complete dose curves**. All historical sample IDs, groups and split membership are retained. Dose curves are separated, but the source contains no biological replicate or independent assay identifiers. Nine doses must not be described as nine independently repeated experiments. Early calibration also makes this a conditional forecasting task rather than de novo assay prediction or mechanistic identification.

## P100-076: neuronal firing responses

The source is the exact member `20250611_data/Patch-clamp/figure-2h-FI-curve-data.csv` in the registered archive from the locally retained Zenodo record 12802682. The bounded ZIP reader opens only that CSV, without extracting other source files. Stiffness values explicitly encode kPa; pA for applied current remains inherited from the historical contract and requires source-protocol confirmation. Existing source metadata records CC BY 4.0; curator-documentation terms and final notice review remain pending.

The CSV contains **780 sweeps in 39 recording files, representing 36 date/dish/cell identities across 17 dishes**. Three cells have two recording files: D4S4/C1, D4S3/C4 and D4S3/C6 on 2025-04-18. The recipe preserves both recordings and records their shared identity; it does not count them as independent cells. Condition labels must agree within each recording and across repeated recordings of a cell.

Rows are not consistently stored in sweep order. The reader therefore sorts by the explicit integer sweep identifier while retaining physical CSV row coordinates. Within each recording, six sweeps at -10, -6, -2, 2, 6 and 10 pA provide the calibration mean and last spike count. These precede all 14 selected higher-current sweeps. Repeated sweep IDs, later low-current calibration, unapproved calibration or ambiguous date/dish/recording identity are errors.

The task retains author-marked `y` responses above 10 pA. All 780 rows in this source carry that flag; this does not establish the absence of earlier author selection. Spike count is an **author-derived measurement**, not an independently validated raw voltage measurement. The supplied frequency column and other derived metadata are never model inputs. Independent spike detection, voltage decoding and electrophysiological mechanism remain outside this reader's verified scope.

All **546 task rows** reproduce exactly: **210 train / 70 dev / 266 test-input rows**, using **7 / 2 / 8 whole date/dish groups**. The complete final recording date, 2025-04-18, remains test. The reader rejects a recipe that moves a final-date dish into development or a prior-date dish into test. Cells, repeated recordings and sweeps within a dish remain together. Train/dev share a recording date in part, so this is dish separation within the historical acquisition design, not independent batches or a causal intervention study. Calibration is required separately for each recording, including held-out recordings.

## Reproducibility and adversarial checks

The [installed-wheel verification receipt](NATIVE_BIOLOGICAL_VERIFICATION.json) binds all four registered source assets, exact identities and values, partitions, calibration inventories, reader modules and byte-identical replay of every generated artifact. Private drafts and exact reader snapshots live under `reconstruction-candidates/native-biological-v1` outside the upload roots. Earlier drafts, source snapshots and wheels remain preserved.

Synthetic fixtures vary held-out future responses and excluded fitted/derived fields; exported prediction inputs stay unchanged. Other tests check nonfinite/formula values, missing calibration, missing time, dose aliases and units, repeated sweep IDs, source-quality exclusions, cell-condition consistency and chronological test allocation. Public test-target columns are absent. No API calls or fitting occur.

These are the sixth and seventh portable draft recipes. No scenarios or leaderboard rows are newly admitted by this work. **33 other compact scenarios** still need native reconstruction and source-specific split review. Broader contract validity, rights, scientifically justified perturbation standards, adapter completion, separate scientific review and final release acceptance remain open. Novelty, practical value, independent discovery and external scientific validation remain unassessed.
