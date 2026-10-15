# P100-033 source PPG reconstruction and participant review

This private native draft preserves all historical task rows and partitions. It is not a newly admitted scenario, new acquisition, clinical validation or independent test cohort.

## Registered sources

The release projection identifies the [BUT-PPG PhysioNet release 2.0.0](https://www.physionet.org/content/butppg/2.0.0/), dated 23 August 2024, from Brno University of Technology. The source profile dates acquisition to August 2020–December 2021; downloading it in 2026 did not create new observations. The registered archive SHA-256 is `9b910fc884f63eca1c5d3a00c5710f838e0053dce94f8a02196bd0adc2ffa33c`.

The recipe binds the archive, source facts, acquisition provenance, publisher checksum list and CC BY 4.0 license text. Its exact historical contract and legacy parser specification are also bound. Final source citation/notice packaging and scientific admission remain open. The original 90.95 MB archive stays outside the upload directories; it contains 27,126 members and 213,136,194 expanded bytes.

## Signal custody and unusual source orientation

The reader checks the complete member/RECORDS/checksum inventories. It verifies publisher hashes for every PPG header and binary signal plus both annotation tables and the recording list. It does not decode or use ECG/accelerometer waveforms, QRS annotations, demographic values or human quality annotations as predictors. Sex/age consistency is checked privately to detect conflicts in the three-digit participant mapping; it does not establish independent identity verification.

There are 3,888 PPG recordings from 50 participants. Of these, 3,840 use conventional 300-frame, three-channel headers at 30 Hz. The explicitly named red channel PPG_R is selected after little-endian int16 decoding and each channel's recorded gain/baseline conversion to arbitrary units. Channel order is never assumed. Missing-sample sentinel values, unknown units, layouts, encodings, zero/nonfinite gains and mismatched byte counts fail explicitly.

**The other 48 records declare 300 channels and one frame**, matching the registered source's documented orientation difference. Their signal bytes are zero and the gains/baselines encode the 300 scalar values. The historical task interprets those values in source channel order as a 30 Hz temporal sequence. The reader preserves that interpretation for exact replay and records the layout separately; ordinary WFDB header semantics alone do not establish its temporal validity. Temporal orientation needs source clarification before scientific admission. These 48 records, from participants 100–111, remain in the fixed historical denominator; they are not silently removed or called ordinary three-channel signals.

The original source authors extracted PPG from smartphone video, synchronized signals and segmented recordings. This package does not reconstruct raw video or independently validate those steps. Motion/contact metadata is assumed known when the complete recording becomes available.

## Expanded feature operations and accounting

The prediction origin follows the complete interpreted 300-point segment (10 seconds at 30 Hz). Source normalization, selection and feature extraction use only that segment:

1. Apply the recorded gain and baseline. Remove a fitted linear trend and divide by segment population standard deviation plus 1e-15.
2. Compute the Hann-window periodogram with 4,096 FFT points and no second detrending; select the strongest frequency between 0.5 and 4 Hz.
3. Record that frequency in bpm, its half-frequency proposal and relative local strength, and power concentration within 0.12 Hz of the strongest frequency.
4. Compute full autocorrelation, select the strongest local maximum among lags 7–60, and use the spectral peak only if no local maximum exists. Record bpm and the absolute spectral/autocorrelation disagreement.
5. Append only binary motion presence and the source ear/finger code. Human quality and detailed motion categories stay out of both exported predictors and per-record lineage.

There are **3,888 two-parameter local detrend fits and 3,888 signal-scale estimates**, explicitly counted. There are zero discovery-rule fits or transforms learned across subjects in preparation. The historical rule complexity does not include this substantial signal processing. Perturbation sensitivity remains a diagnostic over prepared features, not a validated measurement-noise or clinical robustness assessment.

The target is the source's ECG-reference HR annotation. Raw ECG never becomes an input; changing its bytes, the HR annotation or human quality flags cannot change reconstructed PPG features. The reader retains 3,058 quality-0 and 830 quality-1 records; it neither filters poor-quality signals nor selects features using reference error. All 1,166,400 interpreted PPG points contribute to the complete inventory.

## Split and scientific scope

Whole participants and every one of their recordings stay together: **32 train / 8 dev / 10 test participants**, yielding **2,334 / 798 / 756 rows**. Source ID prefixes, metadata membership, recordings and historical opaque IDs are reconciled explicitly. Every public development value and permitted test input reproduces exactly. No protected evaluator output is accessed; no test HR annotation or demographic record is exported. The source acquisitions remain retrospective and publicly exposed.

Recording counts range from four to 108 per participant. Repeated segments, potentially adjacent acquisitions and shared device/protocol conditions are not independent people. Equal-participant MAE avoids treating the heavily recorded participants as more independent evidence. Subject separation does not establish new-device, deployment, disease or future-heart-rate generalization. Reference annotation methodology, synchronization, unusual source orientation, condition availability and uncertainties require review before stronger claims.

See `NATIVE_PPG_VERIFICATION.json` for private reconstruction and isolated installed-wheel replay. Existing rules, failures, scores, sample membership and campaign configuration remain unchanged.
