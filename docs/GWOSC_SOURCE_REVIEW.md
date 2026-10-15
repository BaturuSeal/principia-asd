# P100-003: GWOSC H1 native source and timing review

All 252 historical noise-summary forecasts reconstruct exactly from calibrated strain and native quality masks. This private draft is **not admitted** into a new scientific edition. No frozen result, source file, scientific configuration or paid attempt changes.

## Registered source and provenance

The canonical case is P100-003, GWOSC O4a H1 strain and detector-quality masks. The registered file is `H-H1_GWOSC_O4a_4KHZ_R1-1388511232-4096.hdf5`, 129,225,370 bytes, SHA-256 `b0d7ae53435952801347f8bf518bc8ef5a167dfdb790fe562a2214cc2072522a`. Its H1 detector, observatory H, frame `H1_HOFT_C00_AR`, channel `H1:GDS-CALIB_STRAIN_CLEAN_AR`, O4a 4KHZ R1 format and GPS origin are checked directly. The recorded UTC start is **2024-01-05T17:33:34**, not a 2026 observation. The file spans 4,096 seconds, or 68 minutes 16 seconds.

The retained `context/strain_file_api.json` is hash-bound context, not a feature source. Its whole-record summary statistics never enter predictors. The source landing reference is [GWOSC O4a](https://gwosc.org/O4/O4a/). Local scenario provenance records CC BY 4.0. This is existing rights evidence, not completed contributor/notice review or publication authorization. No source was redownloaded.

## Native arrays and safe decoding

The file contains 16,777,216 float64 strain samples at exactly 4,096 Hz and two aligned 4,096-value uint32 masks at one Hz. The nominal source label 4 kHz is not substituted for the actual clock. The reader checks shapes, dtypes, counts, origin, spacing, axis units, source identities and mask-bit names. It allows only built-in deflate and Fletcher32 filters and denies soft/external links, external storage, virtual datasets, unsupported filters and unexpected object measurements. Optional h5py/HDF5 versions and the decoder binary hash are frozen in the replay environment.

Strain is already calibrated and cleaned by the source channel. This reader does not reproduce detector calibration or establish calibration uncertainty. Nonfinite windows would remain explicitly unavailable, never imputed. The original file has 256 eligible 16-second windows; the first four supply history, leaving 252 prediction origins.

## Exact expanded measurement pipeline

For each eligible nonoverlapping window, multiply strain by 10^21 and execute Welch PSD at 4,096 Hz using a periodic Hann window, 8,192-sample segments, 4,096-sample overlap, constant detrending, one-sided density scaling and mean averaging. There are 15 segments per window and therefore **3,840 local mean detrend fits** over this source. No fitted state is shared across windows.

Integrate the PSD by the trapezoid rule over inclusive 30–80, 10–30, 80–200 and 59–61 Hz bands and take the square root. The frequency grid spacing is 0.5 Hz. The prediction target is the next 16-second 30–80 Hz RMS in 10^-21 strain units. Inputs are four earlier RMS values, their median and median absolute deviation, and three other bands from the immediately preceding window. All source slices end at or before the prediction origin; no centered or future filter is used.

This preprocessing is excluded from historical rule-only complexity. Its fits and expanded operations are now explicit; existing complexity metrics are not silently replaced.

## Quality and injection limitations

The historical eligibility rule requires only DATA bit 0, plus injection-mask bits 0, 1, 2 and 4 (no CBC, burst, detchar and stochastic hardware injection flags). It does **not** require bit 3, the continuous-wave injection veto flag. All 4,096 source seconds have injection mask 23, so none has that veto flag. This is not a claim that a particular frequency bin is contaminated; it means an injection-free interpretation is unsupported.

All DATA flags are present. Nine seconds lack burst CAT2 and CAT3 flags; the historical filter retains them. Mask meanings come from the stored Shortnames/Descriptions, not guessed integer values. Applying quality selection to the entire target window is retrospective eligibility, not information guaranteed available at a forecast origin. These records do not establish an alerting or operational forecast pipeline.

## Split, custody and exposure

The original complete-block allocation is preserved: blocks 1–4 train, blocks 0 and 5 dev, blocks 6–7 test. This yields **128/60/64 rows** and **4/2/2 blocks**. Passing the whole-block check does not establish independent experiments or wholly forward development: early block 0 is dev while later blocks 1–4 train.

Thirty prior-window references cross partition boundaries. Every such input is chronologically earlier than its prediction origin. Earlier observed test-block measurements enter later test predictions under this online-history contract; this is not a simultaneous 1,024-second open-loop forecast. Altering the terminal response does not alter any predictor; an internal response affects only the subsequent four eligible input histories. All future-test responses remain absent from exported test tables.

The task measures noise-summary predictability within one already calibrated detector interval. It does not establish astrophysical source recovery, unseen-detector/population transfer, independent discovery or novelty. Sources and references were exposed retrospectively. A new split name cannot create independent evidence.

See `NATIVE_GWOSC_VERIFICATION.json` for exact historical values/IDs/partition parity and isolated installed-wheel replay. UI and static reports carry a contract-bound scope advisory without changing canonical metrics, assignments or outcomes. Final contract, rights/notices, scientific admission and external review remain pending.
