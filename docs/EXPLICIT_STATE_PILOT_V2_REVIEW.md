# Explicit-state Engine: schema and context pilot v2

Verified 13 October 2026, 13:29 UTC. This is a train/dev-only engineering cohort. It does not enter the primary leaderboard or establish scientific performance.

## What changed

The new `principia-explicit-state-protocol-v2-dev` supplies exact role schemas, kernel naming rules and permitted symbols. Its documented context projection removes repeated expanded artifacts while retaining every input, state binding, kernel definition, failed experiment and prior critique. Complete artifacts remain hash-linked in private storage. The unchanged 48,000-byte guard rejects oversized contexts; it never silently truncates inputs or records.

All 41 saved v1 provider-boundary contexts passed offline projection, with the largest context decreasing from 57,688 to 31,032 bytes. No fitting or API calls were used for that check. The numerical backend, selection, model roles, generation settings and resource limits are unchanged. V1 source, outcomes, failures and costs remain preserved under their original identities.

## Assigned outcomes

| Scenario | Execution | Retained candidates | Fits | Optimizer evaluations | Nominated / fixed slots |
|---|---|---:|---:|---:|---:|
| P100-002 | Unsupported: ten inputs | — | — | — | 0 / 3 |
| P100-017 | Complete | 7 | 10 | 230 | 3 / 3 |
| P100-043 | Complete | 9 | 9 | 100 | 3 / 3 |
| P100-051 | Complete | 10 | 10 | 92 | 3 / 3 |
| P100-054 | Complete | 9 | 9 | 89 | 3 / 3 |
| P100-068 | Complete | 8 | 8 | 56 | 3 / 3 |
| P100-087 | Unsupported: fourteen inputs | — | — | — | 0 / 3 |
| P100-090 | Complete | 10 | 10 | 80 | 3 / 3 |
| **Total** | **6 complete, 2 unsupported** | **53** | **56** | **647** | **18 / 24** |

All six supported assignments executed two rounds, accepted and searched kernels, and linked the report to frozen nominations. Three executed fits on P100-017 failed the positive-prediction requirement for its log loss. One P100-054 kernel patch contained unbound literal state and was rejected. These records are retained. Naming, extra-field and undeclared-parameter failures observed in v1 did not recur in this cohort; this does not establish their general absence.

The cohort took **196.87 seconds** and settled **46 requests**: four capability probes and 42 method calls. Cost was **CNY 2.132957**, with no pending or unknown requests in this cohort. The campaign-wide conservative total is **CNY 57.041285 / 3,000**, including CNY 24 across four older unknown reservations and zero pending reservations.

## Verification and limits

[The immutable verification receipt](EXPLICIT_STATE_PILOT_V2_VERIFICATION.json) checks copied runtime/input bindings, all eight frozen outcomes, 24 slots and every cached payload/response hash against the settled ledger. Verification made no API calls, performed no fitting and left the ledger unchanged. Both driver and workers exited normally. The app displayed the v2 protocol identity, live counts and completed P100-017 nominations; cohort-owned jobs do not offer independent resume.

The source suite passes **1,207 tests**, including strict role contracts, invariant numerical behavior, complete context projection, mutation rejection and replay without duplicate dispatch. Installed-worker checks forcibly exit after settled requests 3 and 7, then recover without repeating paid calls or completed fits. Fresh installation, all twelve CLI help paths, numerical fixture and packaged HTTP guards pass.

Six completed assignments versus one in v1 is a protocol-conformance observation on previously exposed development data. It is not a controlled scientific effect estimate, accuracy comparison or model-ranking claim. All model reports remain unreviewed interpretations. Private-test assessment, novelty, practical impact and external review are `not_assessed`. The eight-input support limit remains in force.

The v2 pilot is explicitly selectable through its cohort preparation API/CLI; ordinary interactive development starts still use v1. Next expose protocol selection explicitly in the interactive flow, then apply the state-accounting profile symmetrically to controls and relevant adapters before any new frozen comparison. Historical leaderboard rules and metrics are unchanged. Rights/contracts, three remaining native readers, six preparation defects, seven method adapters and scientific review still block a release-ready claim.
