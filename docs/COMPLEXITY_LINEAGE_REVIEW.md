# Inherited fitted constants: confirmed accounting gap

The 13 October SHED browser review found one reproducible witness in `full-comparison-v5--P100-015--principia_engine-rule-3`. This is an evaluation/engine-accounting issue, separate from the six known data-preparation defects. Frozen rules, assessments, rankings, configurations and campaign runtime remain unchanged.

In the saved submission, trace item 5 contains an executed three-parameter candidate. The critic then copies its three fitted values into a literal input-only expression, retained at kernel-library item 8 in trace item 16. `grammar-round-1` fits two more parameters around that expression. The final Rule Card and complexity function count only the final parameter map, reporting two free parameters and learned-state bytes for those two values. The expanded expression does display all the operations and constants, but the learned-parameter/state accounting omits the three inherited fitted coefficients.

The proper disclosure for this witness is **two final-stage refitted parameters plus three inherited fitted coefficients**. It is not a claim of five identifiable degrees of freedom: nested affine/clipped parameterizations can have dependencies. All three inherited coefficients came from train fitting and reached the critic through development diagnostics; no test-feedback leakage is asserted by this finding. Numerical prediction losses remain reproducible, while full learned complexity and complexity-based Pareto interpretation require review.

`data-reviews/P100-015-embedded-fit-complexity-v1.json` records the exact expressions, coefficients, trace positions and immutable source/Rule Card hashes. That witness does not estimate campaign-wide prevalence. Do not infer that every numeric constant is a fitted parameter, or change frozen counts by guessing from decimal precision.

Before a new scientific comparison:

1. Audit archived methods uniformly for inherited fitted coefficients, train-derived normalization and literal state. Keep the original denominator and outcomes.
2. Version the Rule Card schema and complexity policy to distinguish final-stage free parameters, inherited learned state, shared parameters and fixed scientific constants, with exact lineage.
3. Make learned kernel bindings explicit or reject untraceable fitted-state proposals. Test renaming/inlining invariance and shared-parameter accounting.
4. Freeze the corrected policy and runtime before new submissions. Preserve v5's historical quantitative exports; any retrospective derived assessment is separately identified and cannot repair earlier search/portfolio selection.

The current UI now discloses the specific witness on P100-015. Final release acceptance remains open. This audit makes zero API calls and performs no fitting or score-based method tuning.

## Uniform primary audit — 13 October follow-up

The versioned read-only auditor checked the full manifest, source/runtime hashes, every submission binding and all 40 training-file hashes. All **520 assignments** and **693 rules** remain in the audit: 483 complete and 37 failed attempts, with 653 expressions and 40 tree rules. The tree arrays and rules without an exact match are **not certified free of hidden learned state**. The procedure does not read test targets, score candidates, refit, call a model or change rankings.

| Primary method | Submitted rules | Host normalization matches | Prior-fit expression matches |
|---|---:|---:|---:|
| Fixed symbolic search | 120 | 39 | 0 |
| Principia Engine | 120 | 21 | 1 |
| Tool-using investigator | 47 | 4 | 0 |
| Other ten configurations | 406 | 0 | 0 |

In total, **65 rules across 26 scenarios** match one of the two audited patterns. The 64 normalization rules contain **188 train-statistic scalars counted within rules**; state reused across different rules is not an independent fitting event. These are derived means and standard deviations, not extra final-stage free parameters. The remaining one matches the previously confirmed three-coefficient SHED witness. The old `literal_state_bytes` field records literal representations, but `learned_state_bytes` omits their learned origin and the parameter-only profile cannot represent that distinction.

This is an exact-match **lower bound**, not a complete affected-count estimate. The scanner uses the reviewed frozen host grammar's origin and exact train mean/population-standard-deviation expression. For inherited fit matches it uses whole expanded expressions from saved executed diagnostics, normalizing signs but applying no approximate coefficient matching or algebraic equivalence search. Rounded, rewritten, unrecorded, privately computed or externally learned state can remain unresolved. Engineering cohorts and adapted methods outside the primary matrix need separate audits. No change to the historical search portfolio can be inferred from this retrospective scan.

The complete assignment/rule inventory and witness hashes are in `data-reviews/full-comparison-v5-literal-lineage-v1.json`. Rebuild into a **new** file with `scripts/audit_literal_lineage.py --workspace /path/to/private-workspace --campaign full-comparison-v5 --output /path/to/new-receipt.json`; the writer rejects an existing receipt. The auditor only accepts its reviewed frozen grammar source hash.

## Correction foundation, not completed integration

`engine/bindings.py` implements an opt-in, separately named development policy with hash-bound scalar sources, expanded kernels, shared-state accounting and rejection of unbound literals. `LINEAGE_BINDING_VERIFICATION.json` demonstrates bit-identical execution of the SHED expression on seven synthetic rows with two final-stage parameters plus three inherited coefficients. This is a disclosed engineering fixture, not a new scientific run. See [the contract](EXPLICIT_STATE_BINDINGS.md).

The current live Engine and all frozen outcomes remain unchanged. Host fitter/normalizer integration, model protocol changes, control/adaptation coverage, candidate selection and final evaluator wiring are still required under a **new version**. The revised profile is not authorized for ranking. The interface and static reports explicitly mark historical complexity/Pareto interpretations provisional.
