# hBN lubricant curve source review

This review adds a private, reproducible P100-030 draft. It preserves all original scenario files, task contracts, splits and completed results. It does not admit a new scenario or establish independent discovery evidence.

## Source and observations

The registered local source is Zenodo record **17864405**, DOI **10.5281/zenodo.17864405**. Its record, README and 19,590,034-byte ZIP match their registered hashes. The recipe binds all three assets and the exact selected member hashes. Nothing was downloaded again. The record declares CC BY 4.0 for the data; final attribution, notice packaging and scope review remain pending. Repository metadata has its separate recorded terms.

The bounded reader decodes `CoF dataset concentration.csv`, `CoF dataset functionalization.csv` and `CoF dataset suppliers.csv`. Each has four curve columns and 25 descending speed coordinates, from 500 to 0.2 mm/s. Headers explicitly identify coefficient of friction as dimensionless, an EHD5 ball-on-disk setup, -20% slide-to-roll ratio and 550 MPa pressure. They report glass/100Cr6 contacts; the concentration table specifically names BK7 glass, while the other two say `Sklo`. No more precise material identity is inferred.

The supplier CSV contains **16,383 columns per row**, overwhelmingly empty spreadsheet-export padding. The reader verifies that every cell after the six declared columns is empty before discarding padding; it rejects hidden nonempty columns. Units, labels, curve dimensions, finite values, pressure, contact materials and speed endpoints are checked explicitly. Summary bars, spectra, images and author-derived variability tables never supply target or predictor values.

These are **published CoF curves**, not reconstructed native force/torque acquisitions. Physical replicate IDs, batch identities and the processing chain from sensor signals to the curves are not supplied in the selected tables. The concentration and supplier headers report 26.2 ± 0.4 °C; the functionalization header reports 25.6 ± 0.3 °C. Source resolution, load-cell nonlinearity and endpoint-regime variability are retained as metadata, not adopted as an independently justified perturbation distribution.

## Duplicate identity and fixed partitions

All 12 stored curve columns contain 300 response cells. Full 25-point equality establishes these historical aliases:

- Functionalization PEG → concentration PEG.
- Supplier PEG → concentration PEG.
- Supplier P5 → concentration P5.

There are **nine distinct curves for eight formulations**. Functionalization P5 differs from concentration P5; both remain in the same formulation group and partition. Exact controls repeated across tables are not counted as new observations or proof of physical replication. Their reuse across different reported temperatures further limits temperature-effect claims.

The duplicate map is frozen and verified against the source. New or broken duplicates raise a review error rather than select a new cohort. This uses already exposed source responses for retrospective custody checking; it is not a procedure fitted using blind evaluation feedback.

The original NS and NG formulations remain test. The compact edition selects two development groups from the other six by the original opaque-group hash. The resulting allocation is **four train / two dev / two test formulations**, containing **five / two / two distinct curves**. Legacy leave-formulation-out wording describes the older preparation, not the current compact train/dev procedure. Physical independence across these groups remains unverified.

## Calibration and permitted question

Each retained curve supplies its own measured endpoints: 0.2 mm/s at physical row 43 and 500 mm/s at row 19. Both are available even for held-out formulations, by the frozen contract. The scored domain is **0.28–10 mm/s**, physical rows 31–42, with 12 responses per curve. Neither endpoint overlaps a scored response. The 11 higher-speed interior points per curve are excluded by the fixed task domain, not by model performance.

This yields **108 task rows: 60 train, 24 dev and 24 test inputs**. Speed, endpoint CoF and concentration are the only predictors. Every row retains exact source member, row, column and both calibration coordinates. The reader emits no test targets and accesses no evaluator vault. Source targets remain curator-only. No imputation, normalization, fitting or LLM calls occur.

The supported question is conditional **curve-shape transfer after two-point calibration within this setup**. It does not test an unmeasured lubricant, independent raw sensor reconstruction, causal effects of surface functionalization or a novel friction mechanism. Temperature, physical replication, source preprocessing, units of any discovered formula and a justified uncertainty/stability contract still need scientific review.

## Verification and release status

Public sample IDs, group identities, every development value and all permitted test inputs match the historical tables exactly, with unchanged partitions. The [native replay receipt](NATIVE_LUBRICANT_VERIFICATION.json) records original-file preservation, source/runtime bindings and byte-identical reconstruction from the separately installed wheel. Reconstruction tests independently perturb scored confirmation responses and unscored interior values, check permitted calibration locality, and reject duplicate, domain, metadata and source mutations.

The draft remains outside all three upload roots. Passing reconstruction does not settle source rights or scientific admission, expand the 40-scenario edition or rerank the frozen campaign.
