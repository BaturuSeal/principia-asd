# Agent Laboratory adaptation: engineering pilot review

Pilot `agent-laboratory-pilot-v1` finished on 11 October 2026 at 14:50 UTC. Its eight assigned scenarios remain separate from the completed 520-attempt primary ranking.

## Verified execution

- Seven complete attempts and one `incomplete_method_execution`; no missing attempt was dropped.
- Forty-eight paid model responses across the four declared roles. Offline replay reproduced each original request-payload hash, all handoffs, programs, numerical diagnostics, conformance checks and eight final assessments exactly, using the pilot's frozen runtime. No API calls occurred during replay.
- Fourteen submitted rules have valid deterministic final assessments. This is execution/coverage evidence, not a claim that these rules establish mechanisms or improve every comparator.
- P100-051 did not perform the required structural revision. The conformance gate retained the unsuccessful attempt and excluded its intermediate formulas from ranked submissions.

Receipt: [agent-laboratory-pilot-verification.json](../leaderboards/receipts/agent-laboratory-pilot-verification.json).

## Reporting defect observed in development evidence

In P100-043, Kimi's development report incorrectly describes the numerical fits as using six training points. The actual host event and data manifest record **616 training rows and 125 development rows**; six is only the prompt's example preview. The report's mathematical interpretation also requires scientific checking. Passing the structural conformance checks does not validate model prose.

The frozen report, response and numerical results are preserved. The UI now distinguishes host-verified cohort sizes and computations from expandable, explicitly unreviewed model interpretation. This presentation correction does not modify any submission, request or score.

The separate `agent-laboratory-adaptation-v2` now supplies explicit train/dev cohort and group counts, labels the example preview unambiguously, and requires machine-checkable cohort-size statements in reports. It passed synthetic guards and all eight assignments in the new `guarded-adapters-pilot-v2` cohort. See [the second pilot review](GUARDED_ADAPTERS_PILOT_REVIEW.md). The original report and incomplete outcome remain immutable. Final test scores were not used for this metadata correction.

## Operational summary limitation

The frozen pilot driver writes the canonical export's 520-attempt summary to `completion.json`; that is the primary export size, not this pilot's denominator. `manifest.json`, both freeze maps, `scripts/status.py` and the verification receipt correctly retain **eight** pilot attempts. The guarded pilot uses a new driver that names campaign-local and canonical-export counts separately. Existing completion records remain immutable.

Scientific review, source rights and final publication acceptance remain open.
