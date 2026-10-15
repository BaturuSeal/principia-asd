# Asta AutoDiscovery · Principia adaptation

**Method:** `asta_autodiscovery`, revision `asta-autodiscovery-adaptation-v2`.

## Source and adaptation boundary

Pinned upstream: [allenai/asta-autodiscovery, effa4be80f94e234d3d926f4f24b6aa6064d10e7](https://github.com/allenai/asta-autodiscovery/tree/effa4be80f94e234d3d926f4f24b6aa6064d10e7). The inspected `mcts.py` implements visit-dependent expansion, UCT and ancestor updates; `beliefs.py` provides sampled Boolean beliefs and Beta KL divergence. Source hashes are in [the inspection receipt](../source-reviews/asta-effa4be.json). The [Apache-2.0 license](../../third-party-notices/asta-autodiscovery-LICENSE.txt) and [upstream NOTICE](../../third-party-notices/asta-autodiscovery-NOTICE.txt) are packaged in the wheel. This implementation was written independently; no upstream runtime or Python modules are vendored.

The [AutoDiscovery paper](https://arxiv.org/abs/2507.00310) describes hypothesis search driven by changes between sampled prior and evidence-conditioned beliefs. Our Beta update uses its cumulative counts with a Beta(1,1) base, and its directional-shift criterion. This differs from the pinned production code's default Beta(0.5,0.5), selectable reward modes and larger exploration workloads. These are explicit adaptation choices, not claims of exact upstream reproduction.

This edition supplies a fixed task and compact numerical measurements. The adaptation searches competing formula families within that contract; it does not reproduce open-ended question selection, arbitrary statistical Python experiments, cloud tools or upstream empirical results. It has no live literature step or hidden scientific reasoning from another method.

## Frozen algorithm configuration

- Four hypothesis nodes, at most four expression-program checks; no within-node structural repair.
- Progressive widening permits expansion when a node has no children, or its child count is below `visits ** 0.5`. Otherwise descend by `mean_reward + sqrt(2*log(parent_visits)/visits)`. Stable insertion order breaks ties. Every completed or rejected node adds one visit and propagates its reward to all ancestors.
- GLM nominates each family from training context and the selected branch's actual development experiments, including failures. Exact structural duplicates are rejected. Semantic deduplication/HAC and algebraic equivalence are not claimed.
- The host freezes an operational claim: the nominated expression, fitted on train, has strictly lower dev loss than a frozen training-mean comparator. This does not test the full meaning of explanatory model prose.
- Qwen supplies two separate Boolean-or-null prior samples. Version 2 explicitly permits prior domain knowledge and elicits an expectation about the frozen formula before execution, not verification of an observed result. These calls receive the frozen claim and task metadata, with no train statistics, row examples, planner interpretation, ancestor results or other observer samples. A defensible leaning is optional: null remains an abstention, with no substituted vote or fallback distribution. Only these eight prior requests receive the domain-prior system policy; all other stages retain the supplied-evidence-only policy.
- DeepSeek supplies the numerical program and initial coefficients. Its structure and parameter names must match the frozen hypothesis. The host validates, fits on train and computes the contract loss on all dev rows. Failed/invalid expressions remain recorded; no replacement is silently injected.
- Two fresh Qwen calls receive the same claim plus the executed program, fitted parameters, losses, residual diagnostics and any failure. Null means abstention; it adds no count. Prior votes are not revealed to these calls. The posterior Beta counts combine the prior counts with the evidence-conditioned votes.
- Search reward is `KL(posterior || prior)` only when the mean belief changes across or onto 0.5, with distinct before/after means. Other updates earn zero. Failed experiments and malformed belief responses always earn zero. At least one non-abstained sample in each phase is needed to use a successful experiment's update.
- Kimi summarizes all four experiments and must retain their IDs and the exact host-provided cohort counts. Its scientific interpretation is unreviewed.

This uses **25 model calls**, at most four train fits and at most eight parameters per formula. The common monetary ledger, 32-call outer bound, 40-minute wall limit and 4 GiB bound also apply. Default roles are GLM-5.3 / DeepSeek-V4-Flash / Qwen3.8-27B / Kimi-K2.6 through the already probed SiliconFlow profiles. The two-sample belief estimate is coarse and uncalibrated; separate API calls do not establish statistical independence. No claim of scientific probability, novelty or significance follows from the reward.

Search reward controls which branch is explored. Final rule selection separately uses development predictive error, expanded complexity and structural diversity; final test assessment makes zero model calls. Test evidence never updates this tree or a shared library.

## Required artifacts and failure states

`submission.json:method_evidence` records the configuration, source pin, tree, parent links, visit/reward updates, selection decisions with thresholds/UCT scores, frozen claim hashes, prior/posterior samples, programs, numerical results, failures and every model handoff with input/output hashes. The interface shows the actual tree and expandable evidence, with uncalibrated beliefs labelled separately from prediction loss.

Completion requires four distinct frozen families, at least two root branches and an executed descendant, actual progressive-widening/UCT selection, four locally checked programs, valid belief sampling/update records, at least one successful experiment and a report covering all four experiments with correct cohort counts. A missing requirement yields `incomplete_method_execution` and no ranked rules. Valid intermediate predictions remain available in the retained evidence. Transport or budget failures remain failed attempts; ambiguous paid calls are never automatically retried.

Synthetic tests check the Beta KL against numerical integration, reward-sensitive UCT selection, widening, ancestry and prior isolation, real numerical fitting, zero rewards for failures, abstentions, malformed belief samples, duplicate structures, changed claims, fabricated report references and request-budget interruption. Live engineering comparisons must use a separately frozen cohort; they do not alter the completed primary matrix.

## Initial engineering outcome

The separately frozen eight-case pilot retained seven incomplete attempts and one provider timeout, with zero ranked rules. Its 28 executed train/dev experiments were valid, but all prior phases abstained and therefore failed the observed-belief guard. The mechanism passes synthetic tests; that v1 cohort did not establish successful live conformance. See the [pilot review](../ASTA_PILOT_REVIEW.md). These outcomes must not be presented as a completed baseline comparison.

## Version 2 correction and preregistration

Source inspection of pinned `beliefs.py:get_belief` confirms that upstream prior elicitation uses `use_llm_prior=True`, which explicitly permits domain knowledge. Our v1 shared system message instead required all calls to work only from supplied development evidence. Cached observer reasons consistently described the missing measurements as preventing verification. That conflict is an engineering defect; it does not justify forcing a belief, exposing development outcomes, or changing the completed cohort.

Version 2 changes only the scoped prior instruction and clarifies prior/posterior response semantics. It records the knowledge policy per handoff. The mathematical update, sample count, tree policy, operational claim, conformance guard, models, data and budgets remain the same. Planner prose remains withheld because it may embed data-informed reasoning. The source is copied into a new immutable runtime before a separately named engineering pilot. See [preregistration](../ASTA_EXPECTATION_PILOT_V2.json); all v1 failures remain visible. Live conformance must be established by the frozen records, not inferred from this correction.

## Version 2 engineering result

The separately frozen v2 pilot completed all eight assignments with 24 valid assessed rules. All 200 recorded responses and eight final assessments replay exactly offline. Every prior and posterior sample leaned true (64 per phase), so all 32 branches earned zero surprise reward. The live records establish guarded mechanism execution, not an empirical benefit from surprise-based branching. Synthetic reward-variation checks remain separate. All v1 failures are retained and the primary ranking is unchanged. See [the development review](../ASTA_PILOT_REVIEW.md#verified-version-2-outcome).
