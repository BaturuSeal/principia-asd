# Fixed-control pilot: execution review

The frozen `explicit-state-controls-pilot-v1` finished on 13 October 2026 in 17.908849 seconds. All 32 assignments have immutable terminal records, and all 96 nomination slots remain. This is a retrospective train/dev engineering cohort on the same eight exposed scenarios as the Engine pilots. It has no private-test assessment and adds no public ranking coverage.

| Control | Complete | Failed | Unsupported | Nominations / fixed slots | Fits | Optimizer evaluations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fitted constant | 6 | 0 | 2 | 6 / 24 | 6 | 42 |
| Full affine | 4 | 1 | 3 | 4 / 24 | 5 | 100 |
| Full quadratic | 0 | 0 | 8 | 0 / 24 | 0 | 0 |
| Fixed symbolic library | 6 | 0 | 2 | 18 / 24 | 96 | 1,130 |
| Total | 16 | 1 | 15 | 28 / 96 | 107 | 1,272 |

The verifier checked 104 retained candidate programs and their explicit state bindings, all input/source/configuration hashes, complete checkpoint chains and the cohort submission freeze. Three failed fits are retained. Completed-cohort verification and a repeated launch returned existing records without fitting or dispatch. There were zero API calls and no change to the global request ledger.

## What the failures mean

- P100-002 has 10 inputs and P100-087 has 14. All four current development controls explicitly support at most eight inputs; their eight assignments remain unsupported.
- Full affine on P100-043 needs nine fitted coefficients and exceeds the unchanged eight-parameter ceiling. No feature was discarded to make it fit.
- Full quadratic is incompatible with every scenario in this particular cohort under that ceiling. Its two-input synthetic verification remains valid, but this cohort provides no real-scenario quadratic execution evidence.
- Full affine on P100-017 failed after 17 optimizer residual evaluations because a trial produced nonpositive predictions for the positive-domain logarithmic objective. Two fixed-symbolic fits hit the same domain guard; its remaining candidates permitted completed library execution. These are retained method/domain failures, not a sandbox outage.

The current generic affine grammar is consequently insufficient for guaranteed positive-domain fitting. Any positive-link or constrained variant needs an explicit method configuration and a new identity frozen before execution; it must not replace this failed attempt. Broader bases likewise require a separately justified resource/configuration decision. Equal numerical ceilings do not imply equal work, and full-basis controls must not silently omit inputs.

## Evidence limits and next work

These outcomes establish custody, accounting, compatibility reporting and executed control behavior. They do not establish prediction quality on independent data, superiority over the Engine, novelty, practical impact or scientific admission. The Engine and these controls have separate development cohort identities; a prospective symmetric comparison has not been performed.

Next apply the same explicit fitted-state interface to relevant adapters and freeze the compatible methods, domain policies and datasets for a new symmetric comparison. Preserve all earlier Engine pilots, the 15 unsupported control outcomes and the affine failure. Source rights/contracts, known preparation corrections, remaining adapters, quality-led scenario expansion and separate scientific review still block full release.

Evidence: [preregistration](EXPLICIT_STATE_CONTROL_PILOT_V1.md), [JSON verification](EXPLICIT_STATE_CONTROL_PILOT_V1_VERIFICATION.json), [per-assignment CSV](EXPLICIT_STATE_CONTROL_PILOT_V1_VERIFICATION.csv). The primary campaign remains 520 attempts and 693 rules across 40 scenarios.
