# Compact edition: source and split review

The 40-scenario compact v2 edition is a prepared retrospective research cohort, not a scientifically approved release. This review found two development-partition defects. Their historical records remain intact, with visible advisories; neither failed scenarios nor attempts are removed from denominators.

## Source integrity and remaining scope

[The reproducible receipt](data-reviews/compact-v2-audit.json) binds the exact edition, scenario descriptors, contracts, public inputs and registered source files. All **622 source files across 40 scenarios** match their registered SHA-256 values: 1,740,880,168 bytes checked, no missing or changed files. These are local originals, not new downloads. Matching bytes do not approve inherited license claims or establish scientific independence.

Two source-specific split reviews are complete; **38 remain not assessed at this depth**. All 40 redistribution and scientific-admission decisions remain pending. The prior generic checks establish distinct group IDs and exact target alignment; they did not establish that those group IDs represent the declared independent split unit.

**None of the 40 scenario packages currently has an executable scenario-local reconstruction script.** The project-level curation script depends on inherited private preparation artifacts. Replaying a stored rule and installing the package do not close this raw-data reproducibility gap. Portable, source-bound preprocessing is a release requirement.

## P100-012: aggregation unit differs from split unit

The task aggregates loss by wafer but declares deposition batch as its independent split unit. The hash-verified NIST source README, lines 44–50, assigns wafers 01–03 to deposition 1, 04–06 to deposition 2, 07–09 to deposition 3, and 10–12 to deposition 4. The curation's hash-based wafer split places deposition batches 1 and 3 in both train and dev. Original test wafers remain in separate deposition 4.

The proposed correction uses depositions 1 and 2 for train, deposition 3 for dev and the original deposition 4 for test. Wafer-level loss aggregation is preserved. This candidate repairs the declared partition unit; it does not establish the scientific adequacy of this small batch cohort.

## P100-062: forward timing violated within one trace

The contract requires forward extrapolation within each current trace. In the low-current stream, training spans time 12–12072 while dev spans 3036–6036. Later observations therefore inform fitting before assessment on an earlier dev block. The high-current development split is correctly ordered. Both original test blocks follow all development observations.

The proposed correction assigns the last complete pre-test block of each `(high, drive)` stream to dev and all earlier blocks to train. For low current, train ends at 9060, dev spans 9072–12072 and the unchanged test starts at 12084. The high-current split is unchanged. Timing checks operate per trace; sorting across unrelated trajectories would not be sufficient.

## Corrections and evidence custody

Private draft candidates live in `../../private-workspace/PrincipiaASD-dev-26Oct10/preparation-candidates/compact-v3-split-review-v1/` relative to the project. They contain only reallocated train/dev rows and immutable candidate bindings. The union of development measurements and targets is exactly preserved; group boundaries are not cut. Original test inputs are unchanged, and this review did not access test outputs, final losses or model reports.

The candidates are **not admitted scenarios** and cannot replace data in the completed campaign. A new edition must pass broader contract/rights/reconstruction review and freeze a new comparison before evaluation. Original source data, edition files, runtime snapshots, submissions, numerical receipts and all 520 assigned attempts are preserved.

The new `catalog.splits` checks reject unmapped units, cross-partition dependence, overlapping time blocks, mixed-stream blocks and nonfinite time. Tests also reject mutated candidate artifacts and changed development values. App and static-report advisories bind to exact task-contract hashes; they affect display only, never numerical scoring or selection.

## Reproduce the audit

From the installed project, using local registered source files:

```bash
python scripts/review_data_edition.py \
  --data-root /path/to/ASD-Scenarios-26Oct10 \
  --source-root /path/to/local-datas/_benchmark_100/release_candidate \
  --candidate-root /path/outside/upload-roots/preparation-candidates \
  --output /path/to/new-audit-receipt.json
```

The audit makes zero model calls. A new run should write a new receipt: its acquisition time changes even when every source hash is identical. Existing private candidates are hash-checked and cannot be silently replaced. Next work is source-specific review of the remaining 38 contracts, portable preprocessing, notices and quality-led admission—not additional comparisons against an unreviewed edition.

## Additional source review: P100-070

Native reconstruction of both magnetic maps preserves every historical row and score. Five of six CSH 200-row development strips span train and dev, contradicting the whole-strip statement in the task contract. CSL remains entirely held out; target pixels do not enter any predictor stencil. Record this as a preparation defect requiring a separately reviewed split contract and new frozen comparison. It is not repaired by reconstructing the original allocation. See [source review](MICROSCOPY_SOURCE_REVIEW.md) and [verification](NATIVE_MICROSCOPY_VERIFICATION.json).

## Additional source review: P100-019

The native complaint file has 185,256 complete physical TSV records, each with 51 fields. Historical quote-aware parsing merges 29 narrative spans, absorbs 176 records and loses 114 unique vehicle complaints after deduplication. Literal record parsing changes 81 vehicle-month counts within the scored cohort, although cohort membership and complete-month boundaries remain unchanged. This is a sixth confirmed preparation defect, not a method failure. Preserve all historical outcomes and denominators; require a separately versioned corrected source reader, data/evaluator package and frozen comparison. The new native draft intentionally reproduces historical values and records the failed literal-record equivalence gate. See [source review](NHTSA_SOURCE_REVIEW.md) and [replay receipt](NATIVE_NHTSA_VERIFICATION.json).
