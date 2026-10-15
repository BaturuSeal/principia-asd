# Frozen task evaluation

Discovery receives train and dev only. Inputs, grouping, target semantics and metric are fixed by the task contract. Native measurement lineage and inherited calibration are retained in the scenario package. Related groups do not cross train/dev/test; learned scaling in a rule is estimated from train and expanded into the expression.

A submission includes its rules, complete expression/tree state, diagnostics, unsuccessful candidates, model trace and accounting. `submission-freeze.json` pins that artifact and its context. Campaign assessment waits until every assigned submission is frozen. The evaluator joins protected targets by sample identity and checks group and content hashes; it never relies on row order. No model call occurs during final assessment.

## Quantitative profile

- **Accuracy:** MAE, RMSE, Brier loss or natural-log MAE, as declared. Groups receive equal weight. Invalid or partial predictions have no rankable primary loss. The comparison gate is the frozen train-mean predictor on the identical full test cohort.
- **Complexity:** expanded weighted operations, named fitted parameters, literal state, complete tree nodes and learned-state size. A fitted mean counts as a parameter. Kernels cannot hide operations behind names.
- **Sensitivity:** seeded perturbations clipped to train ranges, standardized by train output scale, on at most 512 disclosed test-input rows. Since a justified measurement-error model has not yet been approved for each scenario, this is diagnostic and never influences ranking. It is not a universal claim of physical stability.

A development-selected portfolio is assessed in full. The default table orders eligible rules by primary loss for readability and marks the accuracy–complexity Pareto front; it does not create a cross-scenario scientific score. Failed or unsupported attempts keep their assigned denominator. Group errors are descriptive. Scientific uncertainty, novelty, elegance, prior-art differentiation, practical impact and external validation remain `not_assessed` unless separately reviewed.

All current historical tasks are `retrospective-open-test`, even though evaluator custody prevents the discovery worker from reading targets during a new run. These files cannot supply independent new evidence merely by being split again.
