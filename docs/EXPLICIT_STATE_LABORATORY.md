# Agent Laboratory with explicit fitted state

`agent-laboratory-explicit-state-v1-dev` is a separately versioned development method.
It implements the existing local-context Agent Laboratory adaptation using the
explicit-state fitter. It does not replace the earlier adaptation, its completed
pilots, or the primary comparison. A dedicated worker and module CLI now execute frozen development jobs. The interface offers a separate **Agent Laboratory · explicit-state development**
selection and can inspect its handoffs and learned state. The earlier selectable
Laboratory revision is unchanged. The [live pilot](EXPLICIT_STATE_LABORATORY_PILOT_V1_REVIEW.md)
retains three complete, two incomplete, one failed and two unsupported assignments;
it establishes execution evidence only.

## Scientific workflow

The default exact model roles remain GLM for research/planning, DeepSeek for
engineering, Qwen for critique and Kimi for reporting. The six handoffs are:

1. Review permitted measurements and nominate competing explanations.
2. Plan an initial experiment and a feedback-conditioned revision.
3. Propose the initial expression and train-fitted coefficients.
4. Critique its executed diagnostics, including any rejected program or failed fit.
5. Propose and execute a structurally different program, or repair the first one.
6. Report both experiments and the already frozen nomination set.

There are exactly two possible experiment proposals, no host-generated weak-prior
fits, no hidden kernel-search loop and no automatic model repairs. Train means and
scales have explicit immutable source bindings. Both programs expand those
transforms before complexity is counted; all fitted coefficients are host-owned.
Model-authored numerical literals, fitted-state objects and new kernels are not
accepted. Constant-input normalization failures remain recorded; the original
input remains accessible.

The inherited gateway checks the exact response model/request identity, fixed
generation settings, call/wall limits and the 48 KB context ceiling. Oversized
contexts fail explicitly. All permitted input names, train-state definitions,
earlier handoffs and both experiment packets remain visible. The host uses the
full train/dev cohorts; the first six train rows are only a prompt preview.
Final quantitative assessment makes no model calls or new fits.

## Conformance and recovery

Completion requires six valid structured handoffs, both local program checks,
an executed structural revision and at least one valid experiment. Reports must
cite both experiments, every nominated candidate exactly once, and the exact
host-verified row/group counts. Missing behavior is retained as
`incomplete_method_execution`; request/execution exceptions remain `failed`.
All three nomination slots remain fixed, including empty slots and candidates
from incomplete methods. Every receipt remains outside the public ranking.

The revision guard expands kernels and ignores coefficient names and starting
values, preventing an alias or refit from masquerading as a new structure.
It is a conservative syntactic check, not a proof of algebraic inequivalence;
parameter-sharing changes alone do not count as a structural revision.

The existing append-only journal commits every provider handoff, experiment and
nomination freeze. Recovery restores completed work without refitting. A settled
provider response can be recovered only from its identical, verified cache.
Unknown provider or local numerical work blocks automatic replay. Reporting
happens after the host is frozen and cannot revise the nominations.

## Development API

```python
from principia_asd.engine.bound_laboratory import BoundLaboratory
from principia_asd.engine.bound_checkpoint import DurableBoundRun

method = BoundLaboratory(
    task, train_rows, dev_rows,
    gateway=provider_gateway, run_id="new-development-identity",
)
result = DurableBoundRun(
    method, private_run_directory,
    provider_binding=frozen_capability_price_and_generation_binding,
).run()
```

This low-level API requires a trusted host and a separately budgeted provider
gateway. It does not itself create an isolated worker or enforce process memory
limits. Do not use it for a scored arbitrary-code run. The product distinguishes
the earlier Agent Laboratory selection from its separate explicit-state development option.

The default envelope is six model requests, two fitting attempts, 4,096 optimizer
evaluations, 40 minutes and one to eight numeric inputs. Numerical expressions
have no filesystem, network or credential operations. Domain-invalid proposals
remain failures rather than triggering an undisclosed transformation.

## Evidence and limits

The installed-package [verification receipt](EXPLICIT_STATE_LABORATORY_VERIFICATION.json)
contains four assistant-produced synthetic cases: normal execution, repair of
an unbound literal, a rename-only revision and incorrect report cohort metadata.
They are engineering fixtures, not paid model trials or scientific results.
Tests additionally exercise every committed boundary, all six settled-provider
recovery boundaries, unknown-work refusal, fixed denominators and zero-fit
assessment. Subsequent real-model execution is recorded in the separate live
development cohort below, including its failed and incomplete outcomes.

The upstream pin, MIT obligations and broader adaptation departures remain in
the [method card](method-cards/agent-laboratory.md). No upstream code was copied
for this module. This adaptation does not implement live literature acquisition,
unrestricted Python/GPU research, paper generation or independent scientific
review. Source rights, task admission and the remaining release gates are unchanged.

## Dedicated development worker

The `principia_asd.laboratory_jobs` module provides `prepare`, `run`, `resume` and
`status`. Preparation requires a private settings JSON with `workspace`,
`project_root`, `data_root`, `leaderboard_root`, and the optional `env_file` path.
The private workspace must be outside all release roots and evaluator custody.

```sh
python -m principia_asd.laboratory_jobs prepare /private/settings.json \
  --scenario /public/scenarios/P100-054
python -m principia_asd.laboratory_jobs run /private/bound-runs/laboratory-ID
python -m principia_asd.laboratory_jobs resume /private/bound-runs/laboratory-ID
```

The worker binds copied contract/train/dev files, their exact permitted columns,
provider profiles, source snapshot, interpreter and dependency versions. Model
profiles are frozen without substitution. Limits are six model requests, two
fits, 4,096 optimizer evaluations, 40 minutes, 4 GiB and the per-attempt monetary
cap. A shared four-worker limit and one numerical thread apply. The price
reservation and unknown-usage rules are the same as the primary ledger.

Only the restricted typed expression language is executed; there is no generated
Python in this adapter. The trusted provider worker needs network access to
SiliconFlow and is **not** an OS-sandboxed generated-code worker. Model-produced
expressions cannot perform filesystem or network operations. Data staging,
input validation and immutable bindings constrain the scientific inputs; they
are not a claim of process-wide filesystem confinement. The fixed non-LLM
control worker and generated-Python routes have their own sandbox requirements.

Resume checks every frozen input, source and configuration before dispatch,
restores committed fits, and only recovers identical cached paid responses.
A full checkpoint-chain verification also guards reads of completed jobs.
`LABORATORY_WORKER_VERIFICATION.json` records installed-worker tests with hard
process exits after settled request 3 or 6: each run retained six unique mocked
dispatches and two fits, without duplication. These are engineering fixtures,
not live scientific results.

## Live development cohort

`EXPLICIT_STATE_LABORATORY_PILOT_V1.json` freezes the eight previously exposed
engineering scenarios, all 24 nomination slots, exact model roles, rates and
input hashes before dispatch. Six scenarios meet the one-to-eight-input limit;
P100-002 and P100-087 remain unsupported without dropping measurements. The
maximum additional allocation is CNY 80, including probes, within the existing
CNY 3,000 cap. This cohort is train/dev-only and never publishes a test score or
updates the primary ranking. Its mutable progress and raw records stay private.

## Interactive selection

Start the local server with its existing arguments plus `--project-root` pointing
to the public code directory. Without this custody setting the development option
is unavailable, with a configuration reason in the API. In Discover, select a
registered or imported scenario, then **Agent Laboratory · explicit-state
development**. The page displays all four model roles, six-call/two-experiment
limits, a maximum CNY12 per attempt, and train/dev-only output. Custom objectives
and Engine protocol versions cannot silently change this fixed Laboratory protocol.

The ordinary CLI also routes `run --method agent_laboratory_explicit` to the
dedicated worker when its private settings include `project_root`. `resume` uses
the saved version; `evaluate` and `replay` refuse these development records.
Interrupted ambiguous work remains blocked, and cohort-owned jobs stay under
their cohort driver. This is an opt-in development workflow with disclosed failures,
not an admitted primary benchmark method.
