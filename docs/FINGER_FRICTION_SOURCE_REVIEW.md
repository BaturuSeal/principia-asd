# Finger-pad friction: source and participant review

This is a private reconstruction of **P100-023.continuation.v1** as projected into the compact edition. It is not the earlier original task. All historical scenario files, partitions, rules and numerical results remain unchanged. The draft is not an additional admitted scenario.

## Source and field meanings

The registry identifies Zenodo **15365365**, DOI **10.5281/zenodo.15365365**, for *A Touch of Stribeck — Finger-Pad Friction in Viscous Liquid Spreading*. All 11 registered local assets match their recorded hashes: the record, README, friction summary, participant measurements, rheology measurements, rheology fit parameters, raw position/force file and four height/Hersey traces. No data were downloaded again. The record declares CC BY 4.0 for the data; final notice packaging, attribution and scope review remain separate gates.

The friction table contains **165 rows: 11 participants × 15 fluids**. Its headers identify median velocity (m/s), median normal force (N), fitted viscosity parameters, Hersey number, viscosity at 500 s^-1, logarithms and median coefficient of friction. There are no duplicated participant–fluid keys. Finger-pad area is derived from calibrated photographs using ImageJ and reported in cm². Hydration is a corneometer measurement in instrument units, with a declared 0–120 range. Neither area nor hydration is inferred from the friction response.

The existing task uses six inputs: supplied Hersey number, fitted viscosity, median speed, median load, hydration and area. The response is the supplied median coefficient of friction. **Hersey and viscosity are author-derived fields**, not additional raw measurements or independent confirmation of the author's scaling law. The reader expands and checks the reported viscosity operation `K * 500 ** (n - 1)` but does not refit rheology or replace the source value.

The fitted-parameter table labels K in **mPa s^n**, whereas the friction table labels the identical numerical prefactors in **Pa s^n**. The native rheology table reports viscosity in mPa s. This is a source-header conflict, not authority to multiply any frozen input by 1,000. A source clarification is needed before asserting an independently verified physical viscosity scale. Existing values and their declared task units are preserved.

## Native acquisition audit

The complete position/force file contains **159,859 rows across 165 contiguous trial blocks**. Every block has exactly one matching participant–fluid summary. The reader verifies the s/m/N headers, all finite force channels, the complete trial panel and exact physical row ranges. All trial clocks begin at zero. The source trial durations span approximately **3.57–28.7 seconds**; there is no assumption of uniform sampling.

**6,161 rows lack all four clock/X/Y/Z cells**, while retaining force values. These rows remain counted and hashed in the source lineage; they are not discarded or interpolated. **44 repeated finite timestamps occur in 13 trials**, with no reversed finite clock. The source does not establish how those missing or duplicate clocks were handled in velocity or friction preprocessing. Computing a fresh derivative or instantaneous CoF without that information would introduce a new measurement definition.

The median of each trial's native Fz values agrees with the published load within **8.89e-16 N**. This verifies the normal-force summary only. It does not independently validate the author’s speed, CoF, Hersey transformation or sensor calibration. Tangential force and full position arrays are not exported as discovery inputs, and the reader never silently replaces the supplied CoF with a force-ratio formula.

All four height/Hersey files are inventoried, with **4,059 rows** in total. They have two header rows, despite the README's general statement of three. Their clocks are strictly increasing; 28 height cells and 13 log-Hersey cells are missing. The rheology table has 21 shear coordinates, 15 fluid columns and nine missing viscosity cells. These auxiliary files remain outside the predictor set; missing values are neither imputed nor used to select participants.

## Partitions and evidence scope

The original participant hash reserves **ID03 and ID06** for test. The compact-edition hash selects **ID02 and ID11** for development. The remaining seven participants are train. This preserves **105 train / 30 dev / 30 test-input rows**, with every participant’s full 15-fluid panel contained in one split. Stable sample IDs retain the continuation parser’s physical summary-row order.

Every retained row carries its summary row and predictor/response column coordinates, participant measurement row, author-fit row and native trial row range. Public reconstruction emits train/dev responses and test inputs only. Raw sources contain historically exposed responses and must stay curator-only; their availability does not create new independent evidence. The evaluator vault is not read.

The supported comparison is conditional transfer to held-out participants on the **same fluid panel and substrate**, given observed trial summaries. It is not prospective control, temporal forecasting, unseen-fluid or new-surface prediction. Participant separation does not make the shared rheology fits or source-wide experimental conditions independent. The source already studies the Stribeck relationship; recovering it is not by itself novelty.

## Verification and remaining gates

All sample/group identities and partition memberships match the historical public tables. Numerical parity passes the fixed 1e-12 tolerance; 15 floating-point cells differ because of decimal parsing, with maximum absolute difference **9.03e-17**. This is not a claim of bitwise equality with the old pandas tables. The newly generated artifacts themselves replay byte-identically from the separately installed wheel; see [the native verification receipt](NATIVE_FINGER_FRICTION_VERIFICATION.json).

Tests preserve missing telemetry and repeated clocks, exclude perturbed test responses and tangential-force/auxiliary values from predictors, and reject broken source joins, changed partitions, invalid units, malformed domains, hidden columns and ambiguous identities. Original source and scenario hashes remain unchanged.

Scientific admission still requires resolving the fitted-unit conflict, author Hersey calibration and speed/CoF preprocessing, choosing a justified uncertainty/stability contract, and completing rights/notices. Exact historical reconstruction does not close those gates or alter the frozen ranking.
