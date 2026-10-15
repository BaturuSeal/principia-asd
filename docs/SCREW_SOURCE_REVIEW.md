# P100-053 native torque and online-history review

This curator-only draft preserves the existing compact task. It is not a newly admitted scenario, new experiment, independent test set or anomaly-detection result.

## Sources and identity

The registered release projection supplies `scenarios/53_manufacturing_screw_friction/raw/s02_variations-in-surface-friction.zip` and `context/SOURCE_FACTS.json`. The archive SHA-256 is `098322d9cc5ab9969d17ac49d317c2fe398fc906205cb681938d7b9481e7bcae`. The recipe binds both original assets, source identity and historical contract. No numeric-folder-only join is used.

The local source record identifies Zenodo 16031381 (West and Deuse) and CC BY 4.0. The archive README agrees on CC BY 4.0 but displays the earlier DOI 10.5281/zenodo.14729547, version 1.2, updated 2025-04-17. Its cited study concerns surface-based anomalies in self-tapping screws. These identifiers and the disagreement in displayed record versions remain explicit; final citation/notice packaging and publication authorization remain pending.

The archive contains 12,500 operation JSON files, `labels.csv` and a README: 305,863,700 expanded bytes. Native files are read one at a time and not copied into the compact draft. Source data remains unchanged.

## Measurement and complete inventory

The reader verifies 250 workpieces, eight surface conditions, two holes per workpiece, and all 25 reuse cycles per hole. Every JSON cycle, workpiece ID, timestamp and OK/NOK result matches its labels row. Native steps follow Finding, Thread forming, Pre-tightening and Tightening 1.4; early termination is preserved. All 8,679,740 angle/torque/time measurement points are decoded with finite-value, shape and clock checks. There are 25,232 repeated clock intervals. Torque is recorded in Nm, with a direct primary transducer and unit calibration factor. The reader does not reinterpret supplied gradients, control thresholds, final quality decisions or redundant sensor channels as predictors.

Source quality flags retain 9,512 OK and 2,988 NOK operations; NOK does not automatically exclude an operation: 2,856 NOK operations remain eligible alongside all 9,512 OK operations. The fixed target is unavailable for 132 operations: 131 lack the required angle span and one lacks Thread forming. All exclusions retain their source identity and reason. They are not silently relabeled as method failures or imputed.

## Prediction origin, transforms and history

The current-operation prefix ends at the first native Thread forming sample at least 250 degrees beyond its initial angle. This sampled trigger is included. Only record-breaking forward-angle samples contribute, preserving source index lineage. Interpolation is local and bounded: trapezoidal means use fixed 0–250, 0–100 and 100–250 degree windows, with a maximum 35-degree segment. Roughness is the population standard deviation of retained prefix torque at or below 250 degrees. Finding supplies its completed angle mean; its last sample must already be available. No learned transformation or rule fitting occurs.

The response is the trapezoidal angle mean over 700–1300 degrees. The maximum sampled-trigger overshoot is 4.75 degrees and maximum interpolation-to-sampled latency is 1.14 ms. Forward-envelope reduction removes 17,940 nonforward samples in eligible Thread forming traces; it does not reorder acquisition clocks.

History is grouped by workpiece and hole, ordered by source timestamp with strictly increasing reuse count. Only eligible completed earlier operations contribute previous, first and mean-past torque. Missing history falls back to the current prefix as the original contract specifies. No other hole, workpiece or future operation contributes. Source timestamps have one-second resolution; their timezone and start-versus-completion origin are undocumented. The reader uses a timezone-independent wall-clock coordinate and conservative two-sided bounds involving the entire operation duration plus one second at each end. All 11,868 history links pass; the minimum margin is approximately 12.906 seconds. This is an explicit bounded interpretation of source timing, not independent clock calibration.

Earlier completed test-operation responses legitimately enter later test histories under this online one-step contract. The final operation response in a held-out hole cannot change any exported input. Altering an earlier completed response changes only subsequent history for that hole, as required. Test targets are never exported and the protected evaluator vault is never read.

## Splits, parity and scope

The original source-class/workpiece hash selects the held-out workpieces; the compact hash selects development workpieces from the remainder. Both holes and all reuse cycles remain together. There are 160 train / 40 dev / 50 test workpieces and exactly 7,923 train / 1,972 dev / 2,473 test-input rows. Every public value, sample identity, group and partition matches exactly. This is a 12,368-row historical cohort with 132 separately retained exclusions.

All surface conditions occur within the existing setting. Workpiece-held-out grouping does not establish transfer to unseen conditions, stations, materials, manufacturing batches or future periods. The current task predicts late torque conditional on measured prefixes and online history; it does not evaluate source anomaly classes, final tightening quality or causal friction mechanisms. Expanded rule complexity excludes the sensor/feature pipeline, and perturbations remain diagnostic. Those limits appear beside the unchanged results. No new admission or performance claim follows from parser parity.

See `NATIVE_SCREW_VERIFICATION.json` for source/runtime binding and installed-wheel replay, `SCREW_UI_VERIFICATION.json` for actual browser journeys, and the recipe for immutable source hashes.
