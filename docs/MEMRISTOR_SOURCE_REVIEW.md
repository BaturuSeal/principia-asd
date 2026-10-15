# Memristor forming-branch source review

This review reconstructs a private draft of P100-022. It preserves the original 40-scenario edition, contracts, assignments and results. It does not admit an additional scenario or establish independent scientific evidence.

## Source custody and measurement inventory

The source registry binds two local assets: the Zenodo v1 record and its 6,534,354-byte `dataset.zip`. The selected members are `dataset/Figure 3(a).xlsx` and `dataset/Figure 3(d).xlsx`; the recipe also records the README member hash. No raw data were downloaded again, and author simulation code is neither executed nor copied.

Each selected workbook contains 50 adjacent voltage/current column pairs, with 500 complete numerical rows per pair: **100 stored traces and 50,000 measurement pairs** in total. There are no formulas in those cells. The Br-rich workbook has 4,000 additional rows containing a `--` marker in column B and no complete pairs. These are recorded as missing ranges, without inventing measurements or counting them as extra trials.

The workbooks have no device labels, unit headers, acquisition timestamps or batch identifiers. Their historical parser interprets paired columns as volts and amperes. The new reader preserves that convention and converts current to microamperes explicitly; it does not claim that the units were verified from native headers. Worksheet column positions are source trace IDs, not independently verified physical device identities.

## Preserved selection, duplicate identity and partitions

The first 100 complete pairs of every source trace have strictly increasing positive voltage, with the final coordinate below 1.0 V. Exactly 95 of those pairs meet the frozen `voltage >= 0.05 V` domain. Later sweep measurements, author-fitted states, derived resistances, current calibration and threshold estimates never become predictors. Voltage and composition are the only inputs.

`Br-device-05` and `Br-device-04` are byte-identical across all 500 voltage/current pairs. The historical alias is preserved, leaving **99 distinct stored traces and 9,405 task rows**. The alias map is frozen in the recipe. A changed alias or unexpected additional duplicate raises a review error rather than silently changing sample membership. This retrospective identity check uses already exposed full source traces, including later responses; it is not a prospective procedure learned from hidden evaluation feedback. Exact trace equality does not by itself prove that the columns originated from the same physical cell.

The original hash policy retains ten test traces per composition. The compact edition reserves 15 of the remaining traces for dev, producing **6,080 train / 1,425 dev / 1,900 test-input rows**, across **64 / 15 / 20 groups**. Every identity, value and partition matches the frozen public tables with zero floating-point differences. The inherited observation text mentions the legacy five-fold policy; the compact edition instead uses one whole-group train/dev allocation. Those two protocols must not be conflated. Historical contracts and numerical records remain unchanged.

## Scientific limits requiring admission review

The [published article](https://advanced.onlinelibrary.wiley.com/doi/abs/10.1002/admt.202502152) describes Figure 3 as initial-forming curves from 50 cells per composition, measured with a Keysight B1500A under 1 mA compliance. The local README instead names an Autolab PGSTAT204 and acknowledges processing in several software packages. The checked sources do not resolve that instrument discrepancy or the exact processing applied to these headerless workbooks.

The retained task contains **1,852 negative current values** and **3,181 values exactly equal to 1.15 mA**. Both remain unchanged. No noise removal, clipping correction or response-based pruning is introduced. The repeated level warrants checking against the reported 1 mA compliance; it does not alone identify the cause. Prediction of an instrument-limited curve cannot establish a transport mechanism without an appropriate measurement model and independent evidence.

Complete trace separation does not establish independence across fabrication batches, instruments or laboratories. Physical device provenance, units, compliance behavior, valid perturbations and the scope of transfer still need review. These are documented limitations, not newly invented corrections to the frozen task.

The [registered Zenodo v1 record](https://zenodo.org/records/17278410) has a newer revision, but this reconstruction remains pinned to the local v1 hashes. The local metadata records CC BY 4.0 for the archive; final attribution and notice packaging remain pending. No later data version is silently substituted.

## Verification

[Native replay verification](NATIVE_MEMRISTOR_VERIFICATION.json), completed at **2026-10-12T09:03:19.891440+00:00**, confirms exact historical public-cohort parity, unchanged original scenario files and byte-identical replay of every generated artifact from the separately installed wheel in isolated Python. No evaluator vault, provider call or fitted state is used.

The private draft occupies **3,028,805 bytes expanded / 2,472,456 stored**, including full source coordinates and replay metadata; raw acquisitions are not bundled. Missing source rows use lossless ranges. Earlier drafts, reader snapshots and wheels retain their original runtime bindings.

The full suite passes **404 tests**, including 27 new checks for whole-trace identity, duplicate-map mutation, confirmation/later-response input independence, signed currents, stored-cell and formula guards, branch/domain checks, missingness and bounded archive decoding. Ruff, JavaScript syntax, installed-package CLI/numerical/server checks and HTTP security checks pass. The native draft remains **not admitted** until the remaining gates are resolved.
