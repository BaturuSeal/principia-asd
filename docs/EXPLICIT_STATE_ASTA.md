# Asta on explicit host state — development API and worker

This separately identified adaptation uses policy `asta-explicit-state-v1-dev`.
It preserves the existing four-node Asta search while replacing implicit numerical
state with the audited host-owned representation. It is not enabled as a new UI
method, included in the primary ranking, or claimed to have live model conformance.

## Algorithm and provenance

The pinned source is AllenAI Asta AutoDiscovery revision
`effa4be80f94e234d3d926f4f24b6aa6064d10e7`, Apache-2.0. See the
[existing method card](method-cards/asta-autodiscovery.md) and
[source review](source-reviews/asta-effa4be.json). No upstream implementation is
vendored in this change. The local independently implemented progressive widening,
UCT selection, Beta update and ancestor propagation functions are reused unchanged.

GLM nominates a structure, two isolated Qwen requests supply prior expectations,
DeepSeek supplies exactly the frozen program, the host executes it, and two fresh
Qwen requests assess its recorded evidence. Repeat for four nodes, freeze three
nomination slots, then let Kimi report every experiment. There are at most 25 model
requests and four fitting attempts. No Engine weak-prior fits, grammar patches,
local compositions or hidden scientific reasoning are used. Exact profiles and
prices are bound by the dedicated development worker before dispatch. A separate
live pilot and conformance receipt remain required before interactive enablement.

The host computes input normalization on train and retains each scalar's source.
It also records the training-response mean used solely as the comparator.
Expanded rule complexity counts the state actually used by each rule; comparator
state is retained separately, not credited as a candidate or omitted from the
run's computational provenance. No earlier fitted candidate is silently promoted.

Prior requests receive task metadata, a symbolic expanded expression, parameter
names and transformation semantics. They receive no data previews, cohort sizes,
train statistics, initial coefficients, planner prose, ancestor outcomes or other
observer samples. Fixed arithmetic constants may be disclosed. Posterior requests
receive only that claim and its executed experiment. Domain knowledge is permitted
only for priors. Samples are uncalibrated model opinions; separate requests do not
establish statistical independence.

Prior/posterior updates determine a directional Beta KL search reward. Failed
experiments, malformed samples or wholly abstaining phases cannot earn reward.
Every processed node propagates its visit and reward through ancestors. Final
nomination uses the existing train/dev loss, expanded complexity and structural
diversity policy independently of the search reward. Three slots always remain.

## Integrity and scope

Frozen formula text and parameter names cannot change after prior elicitation.
The host rejects literals, hidden fitted state, extra fields, repeated expanded
structures and parameter-renaming duplicates. Shared-parameter patterns and
different state identities remain distinguishable. Failed experiments remain
available to descendants; there is no within-node repair or replacement.

All persistent tree state is reconstructed from append-only checkpoints. Committed
fits are restored without refitting. A settled provider response may be recovered
only under its exact saved payload. Unknown provider or local work blocks recovery
without redispatch. Reporting begins after nomination freeze and cannot fit.
Synthetic assessment covers every slot with zero model calls or refits and is
explicitly ineligible for historical/public ranking.

The API accepts one to eight numeric inputs under a fixed task contract. It does
not reproduce upstream open-ended questions, arbitrary Python experiments,
literature search, semantic clustering or large exploration budgets. Numerical
parameter uncertainty, scientific novelty and external review remain not_assessed.

## Dedicated development worker

`python -m principia_asd.asta_jobs prepare SETTINGS.json --scenario SCENARIO`
creates a private `asta-…` job. The same module provides `run`, `resume` and
`status` commands with that job's path. This interface does not admit the method
to a leaderboard. Ordinary `evaluate` and `replay` explicitly reject these jobs.

The job stages only its contract, train and dev files. It freezes their hashes,
the copied runtime, interpreter and dependency versions, exact provider profiles,
model roles, price snapshot and resource limits. Maximum limits are 25 model calls,
four fits, 2,400 seconds, 4 GiB memory and one numerical thread; the shared process
pool permits at most four workers. Costs use the existing global CNY3,000 ledger.
Keys belong to the provider gateway and are not written into a job or upload root.

The trusted worker runs typed expressions, not generated Python. The expression
compiler rejects file access, imports, attributes and network operations before
execution. This is an expression capability boundary, not a claim that the
provider process itself is an OS-isolated arbitrary-code worker. It retains the
same macOS runtime/isolation preflight as the other explicit-state adapters.

Recovery verifies the original source/input/profile bindings and the complete
journal. It accepts only an exact saved, settled response for each of the 25
known handoffs. Unknown billing or uncommitted numerical work remains blocked.
Finished runs are verified without dispatch, refitting or repeating tree updates.
The earlier selectable Asta adaptation and all frozen campaigns stay unchanged.

## Remaining integration

A separately frozen live engineering pilot and interactive selection remain
required. Scripted real-scenario payload checks are development fixtures, not
evidence of live model conformance or scientific performance.

## Verified engineering evidence — 14 October 2026

The full suite passes **1,626 tests in 302.14 seconds**. New checks cover all
43 committed operation boundaries and all 25 settled provider-response boundaries,
unknown-work refusal, prior isolation, failed-experiment propagation, frozen-claim
binding, shared parameter identity, constant/fitted-state accounting and all three
nomination slots. A fitting-budget exhaustion initially counted as a complete
algorithm; it now records the failed experiment and stops without further requests.

The installed-wheel [verification](EXPLICIT_STATE_ASTA_VERIFICATION.json) uses five
scripted synthetic cases: complete execution, a retained domain failure, prior
abstentions, a changed frozen claim and an incorrect cohort report. It retains
19 fits, 168 optimizer evaluations, 1 failed numerical fit, and 15/15 fixed
nomination slots. These are engineering fixtures, not independent scientific trials.
Every synthetic assessment makes zero model calls/refits and remains unranked.

Ruff, JavaScript syntax and cold-install checks pass. The existing discovery and
leaderboard browser views work without console errors. No new interactive Asta
method was enabled, no live model called and no frozen campaign changed.

## Installed worker acceptance — 14 October 2026

[Worker acceptance](ASTA_WORKER_ACCEPTANCE.json) records 1,696 passing tests
(383.97 seconds), Ruff, JavaScript syntax, cold-installed CLI/security checks and
110 package files identical to source. The unchanged product UI was checked in
the actual browser after its safe idle restart.

Five separate installed child-process proofs exit after settled requests 1, 3,
4, 6 and 25. Each resumes with exactly 25 unique mocked dispatches, four fitting
attempts, 37 optimizer evaluations and three fixed nomination slots. No request,
fit or tree update repeats; a terminal read leaves the result unchanged. Tests
also retain unknown billing, block uncommitted local work, reject source/input/
capability mutations and disallow file/network expressions before execution.

The separate [context preflight](ASTA_WORKER_CONTEXT_VERIFICATION.json) retains all
eight engineering scenarios and 24 slots. Two wide-input scenarios are unsupported.
Six compatible cases execute 150 scripted requests, 24 fitting attempts and 207
optimizer evaluations. Their largest prompt is 27,725 bytes, below the frozen
48,000-byte limit. Five complete; P100-017 remains incomplete because the scripted
formulas violate its log-loss positivity requirement. This is a retained fixture
failure, not evidence about live model performance. No final-test data or provider
call was used; full private results stay outside the upload directories.
