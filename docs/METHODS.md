# Method mechanisms and conformance

Executable methods consume the train/dev task contract. Admitted assessment paths freeze their rule portfolio before test evaluation; explicit-state development paths stop at the nomination freeze and have no private-test ranking. A method returning no legal rule is failed; an unavailable integration is unsupported. A registered name alone never establishes execution.

| Method | Executed behavior |
|---|---|
| Mean | One fitted train mean, represented as one parameter |
| Linear | Train least-squares on the declared inputs; coefficients expanded |
| Polynomial | Train degree-one and degree-two fits; dev selects the result |
| Decision tree | Train depths 2, 3, 4, 6; dev selection; every node exported |
| Fixed symbolic search | Bounded transform/interaction composition, train fitting and development selection |
| Direct | One exact-model response, one expression, local coefficient fit; no model repair |
| Best of 3 | Three independent proposals, train fits and development portfolio selection |
| Feedback refinement | Three proposals with real preceding residuals and failed-candidate feedback |
| Tool investigator | Model chooses inspect, fit, search or finish actions; host executes each action |
| Adaptive Primitive Search (APS) | GLM kernel drafts, local composition, Qwen critique, DeepSeek revision, Kimi evidence summary |
| Agent Laboratory · Principia adaptation | Six recorded research/planning/engineering/critique/revision/report handoffs, two locally checked programs and mandatory structural revision; [method card](method-cards/agent-laboratory.md) |
| data-to-paper · Principia adaptation | Contract-checked statistical plan, executed analysis, critique and computed-reference report guards; [method card](method-cards/data-to-paper.md) |
| Asta AutoDiscovery · Principia adaptation | Four-node branching search with progressive widening, UCT, real experiments, isolated prior sampling, evidence-conditioned Beta updates and propagated surprise rewards; [method card](method-cards/asta-autodiscovery.md) |
| AgentRxiv · Principia adaptation | Two isolated laboratory cycles publish completed reports; a peer report is retrieved and its full formula is expanded into an executed and revised follow-up; [method card](method-cards/agentrxiv.md) |

The Engine starts with the same frozen operator allowlist and an empty scenario kernel archive. It uses two proposal rounds and a separate critique pass. A kernel may only name declared inputs and audited numerical operators; all expanded expressions are retained. Commutatively identical terms are deduplicated. Portfolio selection retains development Pareto trade-offs and structural diversity, up to three rules.

Default model roles are `zai-org/GLM-5.3` (planner), `deepseek-ai/DeepSeek-V4-Flash` (coder), `Qwen/Qwen3.8-27B` (critic), and `Pro/moonshotai/Kimi-K2.6` (reporter). Exact text/JSON profiles passed fresh account probes. Native tool calling and vision have not been claimed or silently substituted; the current method tools are bounded host JSON actions.

## Explicit-state development methods

The interface separately offers **Adaptive Primitive Search (APS) · explicit-state development**
(protocol v2 or original v1) and **Agent Laboratory · explicit-state development**
(Laboratory v1). They use host-bound fitted coefficients and train statistics,
expanded expressions, fixed nomination slots and durable recovery. They do not
replace their earlier versions or completed comparisons. Laboratory requires the
server's public project root, six model handoffs and two proposed experiments;
its separate live pilot retains incomplete handoffs and a truncated report.
See [Laboratory worker and pilot](EXPLICIT_STATE_LABORATORY.md) for the precise
limits, custody model, evidence and known failures.

The [data-to-paper explicit-state development API](EXPLICIT_STATE_DATA_TO_PAPER.md)
now implements guarded analysis, conditional repair, deterministic statistical
replay and computed-reference reporting on the same host. Its dedicated worker and traceable run monitor are implemented; the first live pilot
failed flat planning-schema conformance in all six supported cases. Interactive
selection remains disabled pending a separately versioned correction. Synthetic verification does
not add a live-model baseline or change the earlier data-to-paper cohort.

## Pending integrations

PySR, SINDy, LLM-SR, SR-LLM, FunSearch-style evolution, AI Scientist-v2 and InternAgent remain unavailable pending faithful implementation, source/license pinning and distinct algorithm conformance. Completing these is remaining proposal work. The interface displays this status, and earlier fictitious lifecycle traces cannot be used as implementation evidence.

Parameter uncertainty, dimensional legality beyond explicit units, causal identification and scientific originality are not established by the current numerical search. Those limitations remain visible in Rule Cards.

[Paper v2](EXPLICIT_STATE_DATA_TO_PAPER_V2.md) is a separately versioned response-
format correction under development. It preserves the v1 scientific loop and
strict guards; historical results are not reinterpreted or reranked.

The separate **data-to-paper · explicit-state development** menu/CLI entry now
starts the strict v2 protocol. The [live pilot review](EXPLICIT_STATE_DATA_TO_PAPER_PILOT_V2_REVIEW.md)
retains two complete, four report-incomplete and two unsupported attempts. This
entry exposes train/dev results only; the legacy execution/evaluator path refuses
it, and prior saved v1 jobs keep their frozen identity.

The [Asta explicit-state development API](EXPLICIT_STATE_ASTA.md) is a separately
versioned implementation of four-node branching, isolated prior/posterior sampling
and surprise-guided selection over explicit host state. It has no new UI/CLI method
entry or live pilot yet; the earlier selectable Asta adaptation remains unchanged.
