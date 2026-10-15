# Guarded adapters: second engineering pilot

`guarded-adapters-pilot-v2` finished on 11 October 2026 at 15:48 UTC. Its 16 assignments cover the same eight development-exposed scenarios as the first Agent Laboratory pilot. This cohort remains outside the primary 520-attempt ranking.

| Adaptation | Complete | Incomplete | Submitted rules | Valid final assessments |
|---|---:|---:|---:|---:|
| Agent Laboratory v2 | 8 | 0 | 16 | 16 |
| data-to-paper v1 | 5 | 3 | 5 | 5 |

All assigned submissions froze before final assessment. Offline replay reproduced all 77 paid request payloads, cached responses, method handoffs, numerical results, conformance checks and 16 final assessments exactly. Replay made zero API calls and did not change the ledger. Wall-clock timings are excluded from deterministic comparison.

Receipt: [guarded-adapters-pilot-v2-verification.json](../leaderboards/receipts/guarded-adapters-pilot-v2-verification.json).

## Development findings

Agent Laboratory v2 supplies full train/dev row and group counts in each handoff and requires an exact machine-checkable cohort statement in the final report. All eight reports passed. This addresses the v1 preview-versus-cohort metadata error; it does not verify all prose or establish the independence of recorded groups.

data-to-paper's five completed analyses passed contract-plan guards, executed numerical fitting, review of actual experiment records and traceable report checks. Numbers in report sections come from a host-computed fact ledger linked to train/dev records and the fitted program. Qualitative meaning, statistical significance and novelty remain unreviewed. The adaptation does not implement the upstream full paper-generation or literature workflow.

Three data-to-paper attempts remain incomplete:

- **P100-017:** the proposed expression produced invalid train/dev output. The repair repeated the structure; the deduplication guard prevented a second fit.
- **P100-043:** the extrapolation expression produced invalid train/dev output. The repair repeated the same program; no valid analysis was obtained.
- **P100-090:** both proposals used `clip`, which is outside the frozen expression language. Both were rejected before fitting.

These are observed development execution failures, not missing results to remove. The recorded generic invalid-domain diagnostic does not establish every underlying cause. A future revision should investigate finite-input diagnostics, expression-domain feedback and explicit repair instructions with synthetic fixtures and permitted train/dev evidence. Any change requires a fresh method version and campaign identity. It must not reuse final-test losses as development feedback or mutate this cohort's inputs, requests, outputs or denominator.

## Interface and accounting checks

The browser exposes planner, coder, critic and reporter settings for both adapters. Every model actually used must pass its capability profile before dispatch. A completed data-to-paper run shows the verified cohort, computed report, expandable computation and content hashes, retained experiment records and a downloadable JSON record.

The new driver completion record correctly distinguishes this cohort's 16 attempts and 21 rules from the canonical primary export's 520 attempts and 693 rules. The previous driver's immutable completion summary is preserved with its documented limitation.

Engineering history retains 304 attempts, including 19 failed and four incomplete outcomes, plus 200 separate superseded controls. No scientific superiority, novelty, independent discovery or publication-readiness conclusion follows from these engineering checks.

## Subsequent domain-feedback revision

`data-to-paper-adaptation-v2` was tested in a fresh eight-case cohort, `data-to-paper-domain-pilot-v3`, on 12 October (Shanghai). It adds structured domain and operator feedback while retaining the same data, fitter, resource limits and one-repair rule. The development diagnosis distinguished a negative prediction under logarithmic loss, a negative base raised to a fractional power, and an unsupported function. No final test outputs were used for the correction.

The new cohort took three minutes four seconds and retained **five complete, one incomplete and two failed attempts**. P100-017 still failed to produce valid predictions. P100-043 and P100-054 encountered HTTP 503 at their Qwen critique request. The five submitted rules have valid deterministic final assessments. This is not evidence of an overall success-rate improvement: the versions have different outcomes and provider failures, and no independent repetition study was performed.

All 27 completed responses were replayed offline. The two ambiguous requests were checked against their recorded payload hashes and error boundaries without redispatch; their CNY 4 total reservation remains counted. All eight final assessments replayed exactly. [Verification receipt](../leaderboards/receipts/data-to-paper-domain-pilot-v3-verification.json).

The total retained engineering history is now 312 attempts: 286 complete, 21 failed and five incomplete, plus 200 separate superseded controls. The primary comparison remains unchanged. The next engineering priority is distinct remaining adapters, rather than repeated paid attempts to turn these unsuccessful outcomes into successes.
