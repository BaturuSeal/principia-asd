# Connected scientific models — local rc6

This iteration expands the local library to **47 curated examples**. Eleven scenarios now have executable connected-equation tasks, compared with three in rc5. Four scenarios are new; four existing scenarios gain richer tasks alongside their original contracts and results. The deployed rc4 website and its release bundle are unchanged.

## What is different

Each equation system is an executable graph of quantities with meanings, units, explicit assumptions and shared fitted parameters. Examples include frictional heat generation → separate heat-loss pathways → thermal storage → temperature change, and pressure drive → Knudsen and viscous contributions → total gas flux. These are actual computations, not decorative intermediate names wrapped around a polynomial.

Known constitutive families are disclosed starting hypotheses. **Scientific equation search** fits and compares these priors without model calls. **Adaptive Equation Discovery (AED)** adds GLM planning, DeepSeek equation proposals and revision, Qwen critique and Kimi interpretation. Training data determine parameters; development residuals, condition-specific errors, failed checks and local Jacobian rank inform revision. Model prose is unreviewed and never determines test scores. Renaming parameters or factoring an identical expanded expression cannot create a new hypothesis.

The interface puts connected-equation examples first, preserves a filter for this collection, and defaults to their richer task while keeping historical tasks selectable. Rule cards show typeset systems, quantity meanings, parameter values, assumptions and local identifiability. Mathematically repeated forms share a group; every method, fit and interpretation remains inspectable. All four model roles are available in AED settings.

## Eight new or upgraded tasks

| Scenario | Status | Connected quantities | Held-out unit |
|---|---|---|---|
| P100-013 · Encapsulant cure | New | Thermal rates, autocatalysis, remaining fraction, conversion rate | Complete heating scan |
| P100-027 · Vapor transport | Added task | Phase velocities, bulk void fraction, radial redistribution | Complete source run |
| P100-043 · Learning dynamics | Added task | Early calibration, conditional loss floor, remaining excess loss | Model architecture |
| P100-049 · Battery rest | Added task | Finite-pulse diffusion, polarization amplitude, equilibrium and residual voltage | Rest trajectory |
| P100-061 · Porous membrane | New | Pressure drive, mean pressure, parallel transport pathways | Temperature condition |
| P100-069 · Gearbox heating | New | Mechanical power, heat flows, conductance and temperature increment | Validation run |
| P100-074 · Kinase biosensor | Added task | Dose response, effective rate and accumulated signal | Concentration condition |
| P100-082 · Soil respiration | New | Thermal activity, root association, water availability and inhibition | Site group |

Native sources were reconstructed without learned preprocessing. The four added historical tasks retain every original sample, group and target. Source-derived conversion, fluorescence and respiration remain explicitly identified as such. No author-fitted curve becomes an input. Test targets stay in the private evaluator.

The largest package is 6.72 MB expanded. All eight have complete source-row lineage, explicit input units and separated groups. Exact reconstruction reproduces **75 public files and 24 evaluator files byte for byte**. Group separation does not establish independence between all physical processes; shared instruments, common corpora and source-derived responses remain limitations.

## What the comparisons actually show

[Open the comparison report](mechanism-review/index.html), [JSON](mechanism-review/comparison.json) or [CSV](mechanism-review/comparison.csv).

The final local inventory retains **96 attempts and 87 frozen rules**: 79 complete executions, 12 failures, one incomplete method execution and four unsupported persistence references. These are engineering cohorts, not a new primary leaderboard campaign.

The development-selected scientific equation models reduce held-out loss relative to the development-selected numerical control on six of eight tasks. They have lower observed test loss than every current numerical control on five: vapor transport, learning dynamics, battery rest, membrane transport and gearbox heating. No uncertainty-supported universal advantage is claimed.

| Task | Equation model test MAE | Strongest observed control test MAE |
|---|---:|---:|
| Vapor fraction | 0.09802 | 0.2034 |
| Later training loss | 0.007563 | 0.02512 |
| Battery voltage | 0.0006675 V | 0.003444 V |
| Membrane molar flux | 0.04364 mol/m²/s | 0.09373 mol/m²/s |
| Gearbox temperature increment | 0.6603 K | 0.7631 K |

The cure model beats the development-selected polynomial but not the tree's observed test loss. The biosensor and soil tasks favor simpler controls. A model-proposed gearbox extension improves development loss but worsens held-out transfer: MAE 1.364 K versus 0.6603 K for the sourced thermal network. This is preserved as a failed generalization, not promoted as a more sophisticated discovery.

Three revised AED attempts completed, one failed algorithm conformance and four stopped at provider errors. Their selected cure and training-loss models remain sourced priors; only the selected gearbox rule is a model-proposed revision, and its transfer is worse. The other tested revisions and rejected graphs remain in the candidate archives. These results do **not** demonstrate that model-generated mechanisms outperform curated scientific models.

## Corrections and provenance

1. The first driver failed during import because a launcher resolved a virtualenv symlink to base Python. No attempt or model request had started. An explicit startup receipt records recovery with the same unchanged environment and runtime.
2. The first eight AED attempts failed: four truncated plans and four HTTP 503 responses. A separately frozen engineering revision used concise role instructions and larger bounded outputs, with the same four model profiles. No request identity was reused; uncertain requests were never replayed.
3. Linear controls exposed a constant-column conditioning defect. A synthetic regression fixture reproduced it independently of test labels. All eight linear and polynomial controls were corrected uniformly in separate zero-API cohorts. The first correction exposed a floating-point constant-column edge case; the final solver uses exact range detection plus training-only centering. `centered-least-squares-v3` is used for current comparisons. Earlier fits remain in the denominator and canonical exports. No equation model was changed after test inspection.

Conservative cumulative accounting is **CNY 78.249922 / 3,000**, including CNY 40 of unresolved reservations and no pending calls. This iteration adds CNY 17.0938395, including CNY 16 reserved for eight provider failures. Actual billing remains subject to reconciliation; the reserved amounts are not claimed as confirmed invoices.

The generic legacy data audit flags a missing `source.evidence` array in these frozen manifests. A [separate source audit](MECHANISM_SOURCE_AUDIT_2026-10-16.json) binds all eight scenario hashes to checked local license records and native source hashes. Technical size, sample, group and hash checks pass. The metadata omission is retained transparently; frozen experimental inputs were not edited. Final redistribution approval remains pending.

## Reproduction and local acceptance

- Data: `../collections/mechanism-pack-v2/data/`.
- Rule exports: `../collections/mechanism-pack-v2/leaderboards/`.
- Private targets: `../../private-evaluator/ASD-Scenarios-mechanisms-26Oct16/`; never upload as public data.
- Frozen campaign runtimes and request receipts: private workspace `local-campaigns/mechanism-systems-local-v2`, `mechanism-systems-local-v3`, `mechanism-controls-local-v4` and `mechanism-controls-local-v5`.
- `scripts/verify_mechanism_campaigns.py` replays all 96 assessments with the corresponding frozen runtime and network disabled. [Replay receipt](MECHANISM_REPLAY_2026-10-16.json).
- `scripts/build_mechanism_report.py` rebuilds this report from immutable exports. No fitting or model calls occur during report generation.
- [Final local acceptance receipt](LOCAL_ACCEPTANCE_2026-10-16.json) records package, tests, browser journeys and preservation checks.

This is a local research and product preview. Independent mechanism identification, scientific novelty, external review, prospective evidence and repeat-run reliability remain **not assessed**. More equations are useful only when their assumptions and predictive evidence withstand comparison.
