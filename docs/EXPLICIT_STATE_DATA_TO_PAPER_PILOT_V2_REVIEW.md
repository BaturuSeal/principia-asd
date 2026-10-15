# Explicit-state data-to-paper v2: engineering pilot review

The eight-assignment pilot finished in **154.47 seconds**. It retains **two complete,
four incomplete and two unsupported outcomes**, with **six occupied nomination
slots out of 24**. The six compatible tasks each executed one analysis; report
failure does not erase its frozen candidate. None enters the primary leaderboard.

| Scenario | Execution | Preserved limitation |
|---|---|---|
| P100-002 | Unsupported | Ten inputs exceed the development protocol's eight-input limit. |
| P100-017 | Complete | All required stages and numeric-provenance checks passed. |
| P100-043 | Complete | First report failed; the permitted report-only repair passed. |
| P100-051 | Incomplete | Both reports referenced quantities outside the computed fact registry and contained unlinked numeric text. |
| P100-054 | Incomplete | Report references did not resolve to the registered facts; the required matched development comparison was missing. |
| P100-068 | Incomplete | Digit-bearing input/kernel names in prose triggered the strict numeric-literal guard in both reports. |
| P100-087 | Unsupported | Its input inventory exceeds the eight-input limit. |
| P100-090 | Incomplete | Both reports retained uncomputed references and unlinked numeric text. |

The flat-plan correction resolved all six planning-schema failures observed in
v1: each compatible v2 task reached executed analysis and methodological critique.
The cohort performed **six fitting attempts and 265 optimizer evaluations**, with
no failed numerical fits. This verifies workflow execution on these exposed
examples; it does not establish method robustness or scientific validity.

The report guard deliberately fails closed. In particular, a supplied identifier
such as `normalized_0` currently triggers its digit rule. This is a conservative
interface limitation, not evidence that the referenced measurement was invented.
Other failures, including uncomputed quantities and omitted comparisons, are
substantive traceability failures. No frozen report was unwrapped, rewritten or
rescored to improve completion. Any future guard or diagnostic change needs a
new version and development cohort. Such a change must distinguish verified
identifiers from unsupported quantitative claims without weakening provenance.

## Verification and cost

The [JSON receipt](EXPLICIT_STATE_DATA_TO_PAPER_PILOT_V2_VERIFICATION.json) and
[CSV inventory](EXPLICIT_STATE_DATA_TO_PAPER_PILOT_V2_VERIFICATION.csv) retain all
assignments. Verification used the manifest's original copied runtime, checked
inputs, configurations, full checkpoint journals, frozen candidates and all
**29 exact inquiry payloads plus four capability probes** against provider
receipts. It made **zero new API calls and zero fits**; the ledger was unchanged.
The cohort cost **CNY 1.453675**, with all 33 requests settled and no new ambiguous
billing. Global spending after settlement is **CNY 60.9629845 / 3,000**, including
CNY 24 in four older unknown reservations and zero pending requests.

Submission freeze: `f060e626378ee7e810761eda38b12bd60f7f4bde08930422b75b7ea53abc0370`.
The primary campaign, earlier engineering cohorts and failed Paper v1 pilot remain
unchanged. No private-test assessment, novelty review or public ranking occurred.

## Interactive use and next work

The separate **data-to-paper · explicit-state development** selection starts v2
with frozen task objectives, four exact model-role settings, up to six requests,
one analysis plus a failure-only repair, and a separate report-only repair.
It requires `--project-root`, verified provider profiles and a private workspace.
Three fixed slots, explicit learned state, incomplete reports and safe checkpoint
recovery remain visible. This is a development option with the above limitations;
it does not replace the earlier adaptation or authorize a ranked comparison.

CLI: `principia-asd run --method data_to_paper_explicit --scenario SCENARIO --settings SETTINGS`.
Saved v1/v2 jobs resume their own bound runtime; they never silently upgrade.
Final-test evaluation of these development records remains prohibited.

Next priorities are remaining explicit-state adapter integration and a symmetric
comparison, plus the independent data/source/admission gates. Report usability
improvements should use development evidence and a new protocol identity.
