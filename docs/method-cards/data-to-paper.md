# data-to-paper · Principia adaptation

**Method:** `data_to_paper`, version `data-to-paper-adaptation-v2`.

## Source and scope

The [upstream framework](https://github.com/Technion-Kishony-lab/data-to-paper/tree/81df14c4b9600466e645c3b2b336cc54daa3df3a) develops research through interacting model and rule-based stages, with statistical guardrails and numerical results traceable to computations. This adaptation pins revision `81df14c4b9600466e645c3b2b336cc54daa3df3a`. The MIT [license notice](../../third-party-notices/data-to-paper-LICENSE.txt), copyright 2024 Technion-Kishony-lab, is included in the wheel. Upstream Python is not vendored.

This is a **controlled-context, restricted-expression adaptation**, not execution of the upstream application or reproduction of its published results. The scientific task and partitions are supplied by the Principia contract. Live literature search, unconstrained ideation, arbitrary Python/statistical-package overrides and complete LaTeX manuscripts are replaced by a guarded analysis and a short traceable development report.

## Algorithm that actually executes

1. The host inventories the declared measurements and full train/dev cohort counts. Six displayed examples are explicitly labelled as a prompt preview.
2. GLM proposes a predictive hypothesis and analysis plan. Deterministic guards require permitted inputs, the original output and metric, train fitting and dev selection. A rejected plan stops before fitting.
3. DeepSeek writes one numerical expression. The interpreter enforces both the plan's input subset and the task allowlist. Parameters fit on all training rows; development loss uses the contract's group weighting. One code repair is permitted only after a rejected or failed program, using its actual error record. Version 2 supplies an explicit operator/arity inventory and metric-derived output requirements. Invalid predictions expose finite ranges, invalid/nonfinite counts, bounded row identities and fitted parameters from already computed train/dev predictions. This diagnostic adds no fitting or prediction execution. Cosmetic repetition of a rejected program is rejected without refitting.
4. The host computes a fact ledger: row/group counts, training and development losses, a matched training-mean comparator, residual spread and fitted-parameter count. Every fact includes its computation identifier, fitted-program hash and train/dev record hashes.
5. Qwen critiques the executed analysis, assumptions and dependence. Its interpretation is not an independent scientific review.
6. Kimi writes report templates containing computed references, such as `{{development_error}}`. The host inserts the exact computed values and rejects unknown quantities, unlinked numeric literals, incorrect cohort counts or an omitted comparator. One report repair is allowed; it cannot refit or alter the analysis.

The default roles are `zai-org/GLM-5.3`, `deepseek-ai/DeepSeek-V4-Flash`, `Qwen/Qwen3.8-27B` and `Pro/moonshotai/Kimi-K2.6`. Execution uses four to six model requests, at most two proposed programs and at most eight free parameters per program. The common global ledger, per-run monetary reservation, 40-minute wall limit and 4 GiB bound apply. Missing capabilities produce explicit errors.

## Required artifacts and incomplete execution

`submission.json:method_evidence` retains the guarded plan, every model handoff with input/output hashes, attempted programs, failed checks, numerical diagnostics, computed facts, report templates, guard results and rendered report. The UI exposes computation sources and distinguishes numerical provenance checks from scientific interpretation.

A missing plan guard, successful analysis, critique of that analysis or traceable report yields `incomplete_method_execution` and no ranked rules. Intermediate valid predictions remain in the retained diagnostics. A provider/transport failure is a failed attempt and is never automatically replayed. Final assessment occurs after the whole assigned cohort freezes and uses no model calls.

## Limits and validation

- Traceability validates numeric literals, references and cohort counts; it does not validate the meaning of qualitative prose or guarantee truthful scientific interpretation.
- Group labels come from the scenario contract. They are not evidence that sampling units are independent. No p-values, significance claim or confidence interval is invented. Parameter uncertainty remains `not_assessed`.
- Dimension legality, calibration, perturbation semantics and source rights retain their scenario-level review gates.
- Supported tasks are the edition's numeric fixed-output contracts. Raw multimodal interpretation, interventions, mathematical proof and general program synthesis are outside this adaptation.
- The execution mechanism differs from Agent Laboratory: one guarded statistical analysis, conditional error repair and a numerically traceable report, rather than a mandatory competing-program revision.

Synthetic tests cover real fitting, target aliases, test-access requests, metric/endpoint changes, failed-program feedback, fabricated statistical quantities, unlinked numbers and report repair without refitting. The separately frozen `guarded-adapters-pilot-v2` engineering cohort retained five complete and three incomplete data-to-paper attempts. Its five submitted rules received valid deterministic assessments. Exact offline replay passed for every completed and incomplete attempt. [Development failures and limitations](../GUARDED_ADAPTERS_PILOT_REVIEW.md) remain visible. This cohort does not change the completed 520-attempt primary matrix.

Version 2 is a development-feedback correction, tested separately in `data-to-paper-domain-pilot-v3` on the same eight engineering-exposed scenarios. Five attempts completed, one remained incomplete and two stopped on HTTP 503 responses; five submitted rules received valid assessments. Unknown-billing requests were preserved without retries. The fitter, candidate limits, data, metric and one-repair policy are unchanged. Synthetic tests verify implicit positivity for logarithmic loss, zero-extra-execution domain diagnostics, syntax/function repair and duplicate rejection. No final-test loss was used to design this revision; both prior cohorts remain immutable.
