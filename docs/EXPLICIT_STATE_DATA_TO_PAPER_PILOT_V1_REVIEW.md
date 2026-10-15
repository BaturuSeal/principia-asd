# Explicit-state data-to-paper pilot v1: execution review

This is a failed engineering conformance pilot, not a scientific comparison.
All eight assigned scenarios and 24 nomination slots remain in the immutable
cohort. Six supported cases stopped as `incomplete_method_execution`; P100-002
and P100-087 remained `unsupported` because they exceed eight permitted inputs.
No rule was nominated, no fit or optimizer evaluation ran, and no private test
assessment occurred. The primary leaderboard is unchanged.

## What failed

Every supported case received one settled GLM planning response. Each response
wrapped its plan under an `analysis_plan` key and supplied additional prose or
model fields. The frozen validator requires exactly seven top-level fields:
`hypothesis`, `inputs`, `output`, `metric`, `fit_partition`,
`selection_partition`, and `limitations`. Therefore all six plan guards rejected
the response before the coder or numerical host ran. The saved prompt includes
that stage contract but lacks an explicit flat-object response example and a
clear prohibition on wrapper or extra keys. Synthetic fixtures followed the schema
exactly and did not establish live-model compliance.

This is an interface-conformance limitation. These observations do not measure
predictive performance, statistical reasoning, novelty or practical value. The
existing v1 guards, prompts, copied runtime, paid responses and outcomes have not
been changed or reinterpreted. No permissive post-hoc unwrapping or replay occurred.

## Verified receipts and resource use

The [verification receipt](EXPLICIT_STATE_DATA_TO_PAPER_PILOT_V1_VERIFICATION.json)
binds the original runtime, all staged inputs, full checkpoint chains, all six
reconstructed planning request payloads and response hashes, and four capability
probe receipts. It confirms terminal resume is read-only and leaves the ledger
unchanged. Verification disabled network dispatch, process launch and fitting.

- Eight terminal outcomes; six incomplete and two unsupported.
- Zero nominations across 24 fixed slots; zero fits and optimizer evaluations.
- Ten settled calls: four probes plus six planning calls.
- CNY0.458912 conservatively accounted; no pending or unknown pilot requests.
- 48.018575 seconds from launch to immutable completion.
- Scientific review and private-test assessment: `not_assessed`.

## Safe next development step

Create a separately versioned response-contract revision, retaining the scientific
algorithm, exact roles, plan validator, numerical budgets, input custody and all
v1 outcomes. Provide explicit flat JSON shapes and complete stage examples, then
exercise malformed/wrapped output fixtures before a new frozen engineering pilot.
Do not enable the explicit Paper interactive selector or include this revision
in a ranked comparison until actual execution conformance is demonstrated.
