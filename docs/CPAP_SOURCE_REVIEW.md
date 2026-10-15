# P100-032 — raw pressure, participant separation and actual clocks

This is a private native reconstruction draft. No historical input, target, split, attempt, runtime or score has changed, and no new scenario is admitted.

## Source and scope

The registered source is the [PhysioNet respiratory and heart-rate dataset, version 1.0.0](https://www.physionet.org/content/respiratory-heartrate-dataset/1.0.0/), published 20 March 2024, attributed locally to the University of Canterbury and PhysioNet. The local acquisition contains sixty raw pressure CSV trials for twenty participants. Its README defines PEEP, PEEP with breath holds and forced expiratory manoeuvres. Each participant has all three trials.

The recipe binds **65 local source assets / 35,803,806 bytes**: sixty raw CSVs, the acquisition calibration script, README, license, original checksums and curator source facts. CC BY 4.0 is recorded; final notices and scientific admission remain pending. Demographics/medical-history records, processed datasets, EIT, ECG, PPG and HRB data are not read or exported by this reader. Original acquisitions are not copied into the upload roots.

## Measurement reconstruction

The raw CSV supplies native computer-clock seconds and gauge, inspiratory-differential and expiratory-differential ADC values. The source acquisition code specifies the fixed conversion:

```text
pressure_cmH2O = ((ADC - 0.1*2**14)/(0.8*2**14/2) - 1)*70.306957829636
```

This is the source sensor transfer over a ±1 psi range, followed by the source unit conversion. It is not a fitted participant calibration or a physiological model. Synthetic endpoint/midpoint tests verify the conversion. The reader executes no source MATLAB and performs no smoothing, clipping, interpolation, flow reconstruction, peak selection or fitting.

All **1,520,000 source rows** are decoded. **10,324 negative-clock, zero-ADC padding rows** and **835 repeated clock intervals** remain inventoried. The acquired clocks are nondecreasing. One ADC cell in `Subject18_FEM_raw.csv`, physical row 2 / column 3, has value 818217, outside the stated 14-bit range. It is preserved as a source anomaly and is used by **zero task inputs and zero task targets**. This observation does not justify deleting any historical eligible row.

## Sampling, lineage and evidence boundaries

The historical task nominates origins at measurement indices 100, 200, and so on, below the last nonnegative clock index minus 20. Gauge inputs use offsets 0, -5, -10, -20, -30, -40 and -50; differential inputs use 0 and -20. Trial flags come from the source filename. The target uses offset +20. All thirteen predictors are available at or before the origin.

The old preparation requires finite selected channels, a +20-sample interval within 200 ±25 ms, and a -50-sample interval within 500 ±25 ms. Four of 15,044 proposed origins fail a clock gate; their exact source rows and reasons remain in the reconstruction receipt. All **15,040 eligible rows** are retained. Actual forecast intervals are **176–223 ms**. The five-sample gauge lag is **25–76 ms**, so names such as `p05` denote nominal delays, not exact physical times. The user-facing timing advisory is bound to the exact unchanged task contract. This is a scope limitation, not a new invalidation of the frozen numerical records.

Each row points to a registered trace index and one-based physical origin/target CSV rows. A shared lineage definition expands every input's row offset and column. This lossless representation avoids repeating paths for all fifteen thousand rows. Exact native timestamps remain recoverable from the bound source. No target value is included in test-input tables or row lineage.

| Partition | Participants | Trials | Task rows |
|---|---:|---:|---:|
| Train | 12 | 36 | 9,010 |
| Dev | 3 | 9 | 2,262 |
| Test inputs | 5 | 15 | 3,768 |

Test participants remain 1, 4, 5, 7 and 20; dev participants remain 9, 18 and 19. All three trials stay with their participant. The compact development allocation and original confirmation are unchanged. Origins within a trial share acquisition conditions and prior history. Held-out participants supply their observed pressure prefix at each origin; this is an online short-horizon prediction task, not a free-running forecast or permanently unobserved response process.

## Verification and limits

[The native receipt](NATIVE_CPAP_VERIFICATION.json) establishes exact sample/group identity, partition membership and **zero numerical differences** against public train/dev values and permitted test inputs. All eight generated artifacts replay byte-for-byte from the separately installed wheel with isolated Python. The private draft is **6,880,041 expanded bytes / 3,101,376 stored bytes**, under the default limit. Reconstruction accesses no evaluator vault and makes zero API calls or rule fits.

Thirty-three new tests cover calibrated endpoints, complete participant/trial custody, exact source rows, current/past boundaries, independent target changes, clock gates, retained anomalies, padding/missingness, source hashes and bounded schemas. The full suite has **566 passing tests**; Ruff, JavaScript syntax, isolated installation, all twelve CLI paths and HTTP security checks pass. [Browser verification](CPAP_UI_VERIFICATION.json) confirms the timing advisory on discovery, leaderboard, Rule Card and release status, all 17 rules and 13 complete attempts, two below-gate rules, and Engine coverage of 3,768/3,768. No new discovery is dispatched.

Physiological resistance/compliance, causal effects of pressure settings, clinical utility, independent novelty and external review remain unassessed. A future exact-time task would need a separately reviewed resampling/measurement-error contract and a new frozen comparison. Existing results cannot be retuned using final feedback. Upstream ADC conversion is disclosed separately from historical rule-only complexity.
