# Adaptive Primitive Search (APS): explicit-state development

Method ID: `principia_engine_explicit`. Protocol revision:
`principia-explicit-state-protocol-v1-dev`. This is an independently written
Principia development method under the repository's MIT license. Each run's
launch and checkpoint manifests bind the exact source files, interpreter,
numerical libraries, task, train/dev inputs, provider configuration and budgets.
It does not substitute for `principia_engine` in the frozen v5 comparison.

GLM-5.3 proposes kernels; DeepSeek-V4-Flash proposes expression programs;
Qwen3.8-27B critiques executed development diagnostics; Kimi-K2.6 reports the
frozen nominations. Two planner/coder/critic rounds include four local
compositions in total. Two weak-prior fits are disclosed. Host code fits every
proposed coefficient on train, selects using dev, expands reusable kernels and
retains failed experiments. Exact role changes are recorded per run, with no
silent model substitution.

Train statistics and inherited fitted coefficients require host-issued source
bindings. The complexity profile distinguishes final coefficients, inherited
coefficients, train statistics, fixed constants and expanded operations. It is
relative to prepared measurements and does not claim full upstream
preprocessing complexity or statistical degrees of freedom.

Limits: one to eight numeric inputs; seven requests; sixteen fits; 8,000
structures; 4,096 optimizer residual evaluations; eight final plus inherited
fitted scalars per expression; forty minutes including downtime; 4 GiB RSS;
one numerical thread; at most four shared local workers; at most CNY 12 per
attempt within the existing CNY 3,000 ledger.

Model expressions run only through the bounded host expression interpreter.
There is no generated arbitrary Python execution or direct model filesystem
access. The worker reads contract/train/dev, has no evaluator stage, and writes
to a private development directory. Credentials remain in the host provider
gateway. The worker process itself is not a generated-code OS sandbox.

Three nomination slots freeze before the report. Partial, failed and unfilled
outcomes remain visible. Missing execution of either round, kernel-search
behavior or valid report references prevents complete conformance. Unknown
provider calls and interrupted uncommitted fitting are never automatically
replayed. Committed operations resume with the original source and inputs.

The UI supports configuration, monitoring, cancellation, checkpoint resume,
Rule Card/source inspection and record download. These runs have **no final
test assessment, public ranking or scientific-review claim**. Offline fixture
conformance and browser usability are verified; a live-model engineering pilot
and symmetric control/adaptation coverage are still pending.

See [the binding contract](../EXPLICIT_STATE_BINDINGS.md) and
[UI verification](../BOUND_INTERACTIVE_UI_VERIFICATION.json).
