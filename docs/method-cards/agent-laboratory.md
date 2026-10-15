# Agent Laboratory · Principia adaptation

**Implementation:** `agent_laboratory`, version `agent-laboratory-adaptation-v2`.
This is a constrained adaptation with a disclosed execution contract, not a run of the upstream package or a reproduction of its published performance.

A separately versioned [explicit-state development API](../EXPLICIT_STATE_LABORATORY.md)
now executes the same six handoffs over host-owned fitted-state bindings. It has
synthetic conformance/recovery coverage only; its worker/UI route and real-model
pilot remain pending. The product selection and historical cohorts described
below retain their existing revision.

## Source and obligations

- Upstream: [Agent Laboratory](https://github.com/SamuelSchmidgall/AgentLaboratory/tree/d9017d90e329112d2a80b7712f37ee9094d2cd27).
- Revision: `d9017d90e329112d2a80b7712f37ee9094d2cd27`.
- License: MIT, copyright 2025 Samuel Schmidgall; the [license notice](../../third-party-notices/AgentLaboratory-LICENSE.txt) is retained.
- Basis: the upstream workflow's research review, planning, experimentation, feedback-conditioned program revision and reporting. This implementation was written for the new task-contract runtime; upstream Python is not vendored.

## Required execution

1. GLM writes a research brief with competing hypotheses from permitted local measurements.
2. GLM turns that brief into an experiment plan.
3. DeepSeek generates the initial numerical expression program; the host checks it, fits parameters on train, and computes development diagnostics.
4. Qwen receives the actual experiment record, including failures, and proposes a revision.
5. DeepSeek receives that record and critique, then generates a structurally different program. The host executes the same train/dev protocol.
6. Kimi receives both experiment records and reports development findings with both experiment IDs and limitations.

Default exact model IDs are `zai-org/GLM-5.3`, `deepseek-ai/DeepSeek-V4-Flash`, `Qwen/Qwen3.8-27B`, and `Pro/moonshotai/Kimi-K2.6`. There are six model requests and at most two proposed local programs, with at most eight free parameters each. Invalid programs remain recorded. The global gateway, per-run cost reservation, 40-minute wall limit and 4 GiB worker bound still apply. Model-role changes require a new run manifest; missing capabilities do not trigger substitutions.

All handoff outputs, input/output hashes, program hashes, numerical results, optimizer counts and failures are retained under `submission.json:method_evidence`. A deterministic conformance receipt checks the six handoffs, actual local program checks, a structural revision, experiment references and at least one valid executed program. Missing required behavior yields `incomplete_method_execution` and **no ranked rules**, even if an intermediate formula predicts well. The conformance check establishes control-flow execution, not the truth of the model's interpretation.

Version 2 also supplies exact train/dev row and group counts to every handoff, explicitly labels prompt examples as a preview, and requires the report's structured cohort counts to match the host counts exactly. Incorrect cohort metadata makes the execution incomplete. Qualitative model prose remains unreviewed. This change responds to a development-report error, not final-test performance; version 1's source, reports, submissions and assessments are preserved.

The portfolio contains up to two structurally distinct programs selected before private-test assessment. Parameter fitting and assessment use the same audited backend as the other methods. The deterministic evaluator makes no model calls.

## Adaptation boundaries

- The upstream live literature phase is replaced by a controlled local research brief. No literature novelty assessment is claimed.
- Unrestricted Python, GPU training, external downloads, `mle-solver`'s larger search and LaTeX paper writing are replaced by two bounded numerical expression programs and a structured evidence report.
- The typed expression interpreter has no filesystem, network or credential capabilities. This does not establish conformance for an arbitrary-Python sandbox adapter.
- The method is supported for the edition's numeric fixed-output tasks. Raw image/audio interpretation, interventions, mathematical proofs, general program synthesis and causal identification are outside this adapter's scope.
- Units, perturbation semantics, uncertainty and scientific originality remain subject to the same open scientific-review gates as the other methods.

## Validation and comparison scope

Synthetic tests check that later model requests actually consume preceding handoffs and executed diagnostics; initial failures reach the revision; duplicate programs, invented experiment references and incomplete budgets cannot pass conformance. These fixtures are assistant-produced engineering tests, not independent scientific evidence.

`agent-laboratory-pilot-v1` is a preserved eight-scenario engineering cohort: seven complete attempts and one incomplete structural revision. Version 2 completed all eight assignments in the separate `guarded-adapters-pilot-v2` cohort on those same engineering-exposed scenarios, with exact cohort checks and offline replay passing. Neither cohort changes the completed `full-comparison-v5` manifest, its 520-attempt denominator or its ranking. These are engineering results; broader frozen comparison coverage and scientific review remain pending.
