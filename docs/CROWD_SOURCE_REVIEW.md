# Crowd-trajectory source and observation-window review

P100-090 has a portable native reconstruction of its complete historical conditional-forecast cohort. All **1,428 rows** match the existing public measurements exactly: **986 train / 172 dev / 270 test-input rows**, in **17 / 4 / 5 whole country/condition groups**. This is a draft for admission review; no historical package, outcome or denominator is replaced.

## Source inventory and units

The locally registered Zenodo record 19592341 contains `ExperimentalData.zip` and source metadata. The archive has 367 entries and 173,171,583 expanded bytes. It remains outside the upload roots. The reader bounds archive expansion, member count and individual member size, and refuses duplicate names, traversal paths, symlinks and encrypted entries. It does not execute the archive's Python code.

The selected **123 crowd recordings** contain **1,842,039 position rows**, with **2,660 recording-qualified track IDs** across **26 country/condition groups**. Track IDs are not a count of independent people. The corpus has no duplicate `(recording, track ID, timestamp)` observations. **64 files declare metre positions; 59 declare centimetres**, converted explicitly by division by 100. Finite negative coordinates remain valid. Missing or invalid selected native measurements cause an error; there is no unreported cleaning or outlier deletion.

Only `Time(s)`, `Id-Ped`, `X` and `Y` are read numerically. Supplied `VX`, `VY` and `Pol`, figure summaries, participant laterality tables, single-pedestrian experiments and source hypotheses are excluded from inputs. Positions are the authors' released tracking coordinates; this does not independently establish the camera tracking, smoothing or annotation pipeline, or its real-time latency.

## Expanded measurement operations

Each file receives an integer-second grid from the ceiling of its first timestamp to the floor of its last. At each grid time, each track uses its latest observation at or before that time, with a maximum permitted age of one second. Older and not-yet-observed tracks are missing. There is no forward interpolation. The greatest selected sample age in the actual source is **0.866667 seconds**.

From those positions the reader computes the instantaneous observed centroid, relative positions, backward one-second secant velocities, speeds and centroid distances. Individual signed angular order is the cross product of relative position and velocity divided by their norm product, only when both speed and radius exceed the frozen `1e-3` thresholds. Frame means, variance, radius quantile and tracked-count density are expanded numerical computations, not fitted primitives. Density counts only currently observed tracks; future-only identities cannot raise it.

Initial calibration is the mean order at **relative grid indices 1 and 2**, using the corresponding earlier positions for backward velocity. The first grid time is 0 seconds in 82 files, 6 in the 40 Japanese files, and 35 in the teen file. These are retained native clocks; the implementation does not confuse a relative grid index with an absolute timestamp. Prediction origins are relative indices 4, 6, ...; the response is mean signed order at the following two integer seconds. Current/past order and calibration use no subsequent grid position.

Shared source-row matrices retain the exact native CSV line used for every track/frame. Per-rule origin indices expand the input prefix, calibration and target coordinates without repeating all histories. No XY arrays or test response values are serialized into lineage. Test outputs are omitted from prepared tables. Raw acquisitions themselves remain historically exposed and curator-only.

## Coverage and dependence

All 123 recordings are inspected. **Seven child recordings are too short to produce an origin after the four-second prefix with a complete two-second response window**: D1 repetitions 2–5, D2 repetition 2, D3 repetition 3 and D4 repetition 1. They are retained in the inventory with their source duration and exclusion reason. All candidate origins from the other 116 recordings have finite features and responses; zero additional origins are dropped. A preserved 1,428-row cohort does not imply coverage of every recorded position or every nominal experiment repetition.

All recording repeats from the same country/condition stay together. The source's `Experiments.pdf`, Supplementary Table 1, confirms varied group sizes and conditions but does not provide a cross-recording physical-participant identity map. Reused track numbers therefore cannot establish independent participants across conditions. One teen condition stays entirely in development, with no held-teen generalization claim. The table lists two teen repetitions, while the archive supplies one B1 CSV; whether it combines repetitions or omits one remains unresolved. Nothing is invented to fill that correspondence gap. Child track counts can also be lower than the table's nominal cohort size, so the density feature describes tracked people rather than total attendance.

The current contract already discloses condition-level grouping and unresolved participant reuse. This source pass finds no new cohort or observation-window correction to apply. Rights and notices, tracking provenance, experiment correspondence and final scientific contract admission remain open. Predictions cannot establish a mechanism for rotation direction, causal influence, or a free-running crowd model.

## Reproduction and tests

The recipe in `configs/preparation/P100-090.raw-v1.json` binds both source assets, the complete selected recording inventory, original parser specification, historical contract and partitions. The [installed-wheel verification receipt](NATIVE_CROWD_VERIFICATION.json) verifies byte-identical regeneration in isolated Python and unchanged source packages. The private draft is stored under `reconstruction-candidates/native-crowd-v1/P100-090`; the full draft is **2,350,919 bytes expanded** (2,161,768 on disk), including source-row lineage and replay metadata. It is not an admitted edition.

Tests cover unit conversion, exact source-row lineage, nonzero clock origins, future-coordinate and future-only-track independence, stale observations, excluded source-derived channels, short and nonfinite windows, duplicate clocks, invalid identities, bounded allocation and unsafe/unregistered archive members. No API calls, model fitting, evaluator-vault access or paid replays occur. The existing application and frozen campaign runtime remain unchanged.
