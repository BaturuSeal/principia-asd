# P100-072 native qPCR and early-calibration review

This private reconstruction preserves the historical task and partitions. It does not admit a new scenario or establish independent confirmation.

## Source custody

The registered projection supplies `scenarios/72_biotechnology_yeast_competition/raw/dataset competencias.xlsx` and `context/source_record.json`. The workbook SHA-256 is `3c1bf733f9bf117bd945ab3f7eb5a1913f88cb85d5eeec4c70211dd00a90918a`. The recipe binds both sources, the scenario descriptor and historical task contract. The local metadata identifies [Zenodo 18757697](https://doi.org/10.5281/zenodo.18757697), Contreras Ruiz, Alonso Del Real, Barrio and Querol, and CC BY 4.0. It links [Food Microbiology 114, 104276](https://doi.org/10.1016/j.fm.2023.104276). Final attribution, notices and publication authorization remain pending.

Native qPCR exports date from 2020; workbook analytical sections date from 2021/2022. The February 2026 deposit is not a new observation date. The legacy audit inspected early spreadsheet rows including later responses across all strains. This remains audit-exposed retrospective evidence.

## Measurements and reconstruction

The workbook has eight strain sheets plus HPLC and HPLCaa. The reader decodes bounded XML directly, without Excel, macros, formula execution or network access. Its one external workbook reference is counted but never followed. Only exact local same-row percentage formulas `(ratio*100)/(ratio+1)` are recognized; shared-formula ranges, cached percentages and stored ratios must agree. The largest cache/ratio discrepancy in the source is 1.42e-14 percentage points. Cached values are preserved, not recomputed for export.

The complete inventory contains 117 qPCR sample rows. Sample Name determines biological replicate and time; worksheet order does not determine replicate pairing. GRE places replicate 3 before replicate 2 at 432 hours. Merged chart-time labels are checked against sample times. Chr96,2 and NCAIM retain stale or ambiguous percentage-column headers; the selected local formula, target/reference markers BUDk/BUDc and source layout establish the historical column mapping, not an independent biological measurement validation.

The response is the author's derived S. kudriavzevii percentage. It is not a directly counted viable-cell proportion, competitive fitness estimate or mechanistic interaction parameter. Same-time Cp, ratio, complementary percentage, replicate averages, HPLC measurements and other responses are excluded from predictors.

## Calibration, missingness and partitions

Each eligible replicate supplies its own 22-hour and 72-hour percentages, used only to predict 96 hours and later. This is forecasting conditional on two biological measurements, not prediction from inoculation or strain descriptors alone. Twenty-one replicate series have both required calibration values.

Three incomplete prefixes are retained in the audit: Chr96,2 replicate 2 lacks 72 hours; Clos replicate 1 and Ec1118 replicate 2 lack 22 hours. Their eight otherwise time-consistent later observations are not eligible. Ec1118 rows 14–16 separately disagree between sample time 504 hours and chart time 500 hours; all three are excluded. Nothing is interpolated or imputed. No rule fitting or learned preprocessing occurs.

The resulting 61 rows are unchanged: 25 train, 18 dev, 18 test inputs. Whole strains, including all replicates and times, remain together: train Chr96,2/Clos/Ec1118/NCAIM, dev GRE/QA23, test T73/D245. Exact sample IDs, group IDs, numeric values and partition membership match the frozen public tables. Protected evaluator outputs are never accessed; native later test responses are omitted from exported data and lineage.

Tests modify later percentages and verify that predictors remain identical; they separately modify one early calibration and verify that only that replicate's later inputs change. Invalid local/shared formulas, future/external references, stale caches, changed target/reference markers, malformed identities, missing measurements, unsafe links and source/partition mutations fail explicitly.

## Admission limits

There are only eight strain groups and two held-out strains. Repeated times and biological replicates do not increase the independent strain denominator. Shared medium, competing CR85 strain and experimental setting limit transfer. The source description's nitrogen quantity of 300 g/L remains unresolved and is not an input. Assay uncertainty, source normalization and biological replication require review before broader claims.

Historical rule complexity excludes upstream qPCR calibration and measurement costs. Perturbation sensitivity remains diagnostic. The task can support a small conditional forecasting comparison; it cannot establish independent discovery, causal competition mechanisms, viability or practical impact. A new reviewed contract and versioned edition are required before admission; existing campaign rules, scores and denominators stay unchanged.
