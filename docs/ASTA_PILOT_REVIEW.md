# Asta engineering pilot v1

## Preregistered engineering scope

`asta-branching-pilot-v1` uses P100-002, 017, 043, 051, 054, 068, 087 and 090, all previously engineering-exposed. Eight assignments use `asta-autodiscovery-adaptation-v1` and the exact default model-role mapping in its [method card](method-cards/asta-autodiscovery.md). The four-node, 25-request algorithm configuration is frozen in the runtime source before the first paid request.

The pilot checks real tree expansion, distinct structures, immutable hypotheses, prior isolation, executed programs, belief updates, ancestor propagation and reproducible records. Any code repair decisions must use synthetic or train/dev evidence only. No success quota, repeated failed request or model substitution is permitted. Incomplete methods and provider failures remain assigned outcomes. It does not establish calibrated beliefs, novelty or upstream reproduction.

All eight submissions must freeze before final assessment. The canonical primary matrix remains 520 attempts and 693 rules; this cohort enters the separate engineering table. The existing global CNY 3,000 cap and CNY 12 per-attempt cap apply, with reservations including unknown usage. There are at most four workers with one numerical thread each. Prior ambiguous requests remain reserved and are not replayed.

Synthetic conformance passed ten tests before launch: actual branching/descendant execution and fit counts; Beta KL against numerical integration; reward-sensitive UCT and widening; malformed samples; duplicate and changed structures; abstentions; fabricated report references; failure retention with zero reward; and bounded request interruption. The whole suite passed 86 tests. These are engineering fixtures, not scored scientific discoveries.

## Observed result and integrity

The pilot ran 17:45:58–17:54:18 UTC on 11 October 2026. All eight attempts froze before final assessment: seven incomplete, one timeout, no complete method executions and no ranked rules. Every successful four-node run had 25 model handoffs and four valid train/dev experiments, but every prior phase returned `[null, null]`. All 28 branches therefore lacked an observed prior, earned zero eligible reward, and failed the preregistered belief-update guard. This is not repaired by treating the Beta base mean as an elicited 0.5 belief.

P100-002 stopped on a Qwen read timeout at request 3. Its CNY 2 reservation remains unknown. Offline verification replayed 177 completed responses exactly, checked that timeout's payload hash without dispatch, and replayed all eight deterministic assessment receipts. [Verification receipt](../leaderboards/receipts/asta-branching-pilot-v1-verification.json). The frozen runtime is `0e6b09b72643ba0227c50ee1920c0f90127536740dc12ef4ebca2e7018f0af95`. Source, data, roles, configurations, completed responses and failures are unchanged.

The cohort added CNY 4.7989385 conservatively, including the unresolved timeout. Global spending is CNY 43.7408855, including CNY 24 unknown reservations, with no pending calls. The primary ranking stays 520 attempts and 693 rules.

## Development interpretation and next gate

The current fixed-target operational claim asks whether a formula will beat a mean predictor on an unseen development set. The observer consistently declined to assert this before seeing evidence. This is useful failure evidence: the numerical search and record machinery run, but the intended sampled-prior mechanism does not yet support a successful live conformance claim.

Review expectation elicitation and the treatment of genuinely uninformative priors against the pinned source. A future change must state its semantics before running, preserve abstentions and distinguish assumed distributions from measured votes; it must not fabricate confidence or quietly relax the existing guard. Test any revision synthetically, then freeze a new version/cohort. No private-test loss is needed or permitted for this decision. Source-rights, scientific-contract and external-review gates remain separate.

The UI explicitly shows unobserved priors, no-reward outcomes, missing requirements, parent links and downloadable evidence. Browser inspection also caught and fixed inline styles blocked by the application's CSP; nested cards now use stylesheet classes without weakening that security policy.

## Source-grounded revision, 11 October UTC / 12 October Shanghai

The pinned source's `get_belief` explicitly permits domain knowledge for prior elicitation (`use_llm_prior=True`) and excludes it for the explicit evidence-only posterior. Inspection of our v1 payload builder found the opposite instruction for priors: the shared system prompt required every role to work only from supplied development evidence. Seven completed request sequences consequently described the absence of measurements as preventing verification.

`asta-autodiscovery-adaptation-v2` resolves this conflict with a tightly scoped domain-prior policy, distinguishing a subjective expectation from an observed result. It does not pass planner reasoning or measurement previews to the prior, assume a fabricated 0.5 vote, change the operational claim, or relax any observed-belief requirement. All 90 tests and Ruff pass, including prior-only policy isolation and unchanged all-abstention failure. The new eight-case cohort is preregistered in `ASTA_EXPECTATION_PILOT_V2.json`; live success remains unverified until that cohort finishes. The earlier outcomes and runtime remain immutable.

## Verified version 2 outcome

`asta-expectation-pilot-v2` ran **18:40:35–18:47:10 UTC** on 11 October (6 minutes 34 seconds). All **8/8 attempts completed** under the original conformance guards and produced **24 valid final rule assessments**. All eight submissions froze before assessment. The new cohort is engineering-exposed and remains separate from the primary ranking. It does not replace the v1 seven incomplete attempts or its ambiguous timeout.

Offline verification replayed **all 200 paid responses and all eight assessment receipts** exactly using runtime `fe72e7fb63ba7608e0a901a785f9d3bad1cce12eedfdcc26229323aaf3b04964`, with **zero API calls and an unchanged ledger**. No request in this cohort failed or remained ambiguous. [Verification receipt](../leaderboards/receipts/asta-expectation-pilot-v2-verification.json).

Across the 32 executed branches, all **64 prior and 64 posterior votes were true**. The observer-prior mechanism now executes, but this pilot exhibits no change of leaning and **zero rewarded branches**. UCT and progressive widening execute with zero observed reward differences; only synthetic fixtures establish that differing rewards alter branch choice. This cohort does not demonstrate useful surprise, calibrated beliefs, scientific novelty or an advantage over other methods. Do not seek such a result through repeated post-hoc reruns.

The cohort cost **CNY 3.3599525**, bringing global conservative spending to **CNY 47.100838 / 3,000**, comprising CNY 23.100838 recorded usage and **CNY 24 unresolved historical reservations**. There are 1,462 completed request entries, four unknown entries and no pending reservations. The four unknown entries remain untouched. Engineering history now contains **328 attempts: 294 complete, 22 failed and 12 incomplete**, plus the separate 200 superseded controls. The canonical primary table remains 520 attempts, 693 rules and 40 scenarios.
