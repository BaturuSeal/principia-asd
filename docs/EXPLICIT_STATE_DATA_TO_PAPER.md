# data-to-paper with explicit fitted state

`data-to-paper-explicit-state-v1-dev` is a separate development Python API. The
earlier selectable adaptation, its completed engineering cohorts and the primary
comparison remain unchanged. A dedicated frozen worker and run-monitor view are implemented. The live pilot
failed planning-schema conformance; interactive selection remains disabled for this revision. It is not a new ranked
baseline or evidence that the complete release is ready.

## Scientific workflow

The method retains the upstream adaptation's defining behavior: a guarded plan,
executed statistical analysis, critique and a report whose numerical literals link
to computations. It uses GLM for planning, DeepSeek for the expression, Qwen for
critique and Kimi for the report, under the existing exact model identifiers.

1. Inventory the complete permitted train/dev measurements and cohort counts.
2. Validate the proposed input subset, output, metric and train/dev roles. An
   invalid plan stops before code generation or fitting.
3. Execute one model-authored expression, with one repair only if it is rejected
   or fails. No host-generated weak-prior fit or formula-search loop runs. The
   expanded expression and its state lineage must use the planned measurements.
4. Freeze the host and all three nomination slots. Normally one slot is filled;
   the remaining two stay explicitly unfilled. Failed and incomplete work remains.
5. Re-execute the frozen program on all train/dev rows, without fitting. Check its
   losses and residuals against the original diagnostics and build a hashed fact
   bundle with exact cohort, program, fitted-state and prediction hashes.
6. Critique that executed experiment and exact fact bundle. Then render a report
   using `{{fact_name}}` references. One report repair may fix guard errors but
   cannot change the already frozen program or nominations.

Every coefficient is fitted by the host on train. Normalization means/scales have
host-owned source bindings; complexity expands those operations and counts their
learned scalars. Numerical literals or externally supplied fitted state cannot be
smuggled into an expression by naming them a kernel. Unlike the Principia Engine,
this method neither evolves new kernels nor composes additional candidates.

## Statistical and report contracts

The bundle records full row/group counts, contract-weighted losses, the matched
training-mean comparator, residual mean and SD, free coefficients, train-statistic
scalars and expanded operator count. Groups receive equal weight in loss
aggregation; RMSE takes the square root afterwards. The comparator's mean is
computed from training targets only and retained as a diagnostic artifact. It is
not an extra candidate or optimizer fit. The host fitter still minimizes its
declared train squared-residual objective; that objective is not necessarily the
contract's reporting loss. No statistical optimality claim is made.

The statistics step separately counts both partition prediction executions,
processed rows, CPU and wall time after the immutable nomination freeze. It adds
zero fitting attempts and optimizer evaluations. Residual SD uses `ddof=0`; it is
descriptive spread, not a confidence interval. Parameter uncertainty, causal
interpretation and sampling independence remain `not_assessed`.

The report must cite the exact facts hash, nominated IDs, full cohort counts and
all supplied plan/critic limitation IDs. Headings, text and extra limitations
reject unlinked numeric characters, unknown references and malformed braces.
Rendered numerical text is withheld when any guard fails. Both candidate and
matched comparator losses are required. The underlying plan and critique prose
remain separately labelled unreviewed. These checks do not validate natural
language semantics, spelled-out numerical claims, citations, novelty or causality.

## Recovery, limits and usage

```python
from principia_asd.engine.bound_data_to_paper import BoundDataToPaper
from principia_asd.engine.bound_checkpoint import DurableBoundRun

method = BoundDataToPaper(
    task, train_rows, dev_rows,
    gateway=budgeted_provider_gateway, run_id="new-development-identity",
)
result = DurableBoundRun(
    method, private_run_directory,
    provider_binding=frozen_capability_price_and_generation_binding,
).run()
```

Default limits are six model requests, two proposed analyses/fitting attempts,
4,096 optimizer evaluations, 40 minutes and one to eight numeric inputs. Calls
usually total four; the two repair branches consume the remaining two. Exact
model/request identity is checked, and contexts over 48 KB fail without hidden
truncation. A cancelled or exhausted run preserves its three slots and failures.

The append-only checkpoint journal restores committed computations and reporting
steps without refitting or redispatch. A settled request can be recovered only
from the identical verified cache payload. Unknown provider or local work blocks
automatic replay, including an interrupted post-freeze statistics computation.

The Python API requires a trusted host and a provider gateway with monetary
reservations. The dedicated worker additionally freezes staged train/dev files,
source, interpreter/dependencies, request, exact model profiles and price snapshot.
It uses the shared four-worker slots, one numerical thread, a 4 GiB watchdog and
40-minute deadline. The gateway owns credentials; expressions use the restricted
interpreter and cannot perform file or network operations. The trusted gateway
process itself needs network access and is not an arbitrary-code sandbox.

Use `python -m principia_asd.paper_jobs prepare SETTINGS --scenario SCENARIO` followed by
`python -m principia_asd.paper_jobs run RUN_DIRECTORY` from the installed package.
The module also supports `resume` and `status`. The generic CLI can safely resume
a bound Paper job but refuses legacy evaluation/replay for these development
records. Run history displays the actual analysis, computed statistics, source
bindings and report guards; a failed report is retained but not rendered as a
validated narrative. The existing selectable data-to-paper method is unchanged.
A separately frozen live engineering pilot is required before enabling the new
interactive selector or broader comparison. Synthetic zero-API assessment is supported by the bound
evaluator, always with a fixed denominator and `ranking_authorized: false`.

## Provenance and verification

Upstream revision `81df14c4b9600466e645c3b2b336cc54daa3df3a` and MIT attribution are
unchanged; the [existing method card](method-cards/data-to-paper.md) and bundled
license describe them. No upstream Python or old runtime is vendored. Shared
host-state, provider and checkpoint components are reused from this package.
Live literature acquisition, unrestricted statistical Python, full manuscript
generation, raw multimodal extraction and independent scientific review are
outside this adaptation.

The [installed verification receipt](EXPLICIT_STATE_DATA_TO_PAPER_VERIFICATION.json)
contains assistant-produced synthetic cases for complete execution, conditional
analysis/report repair, incorrect report cohorts and a forbidden test-selection
plan. They are engineering fixtures, not paid model results. Tests cover source
mutation, unplanned-input state, full-group comparison, unlinked numbers, every
normal committed boundary, conditional repair recovery, cached paid-response
recovery, unknown-work refusal and zero-fit assessment. This does not resolve
scenario rights, scientific admission, units or perturbation-contract review.

The [worker verification](PAPER_WORKER_VERIFICATION.json) exercises hard exits
after settled calls in the conditional analysis repair, critique and final report
repair. Recovery consumes the exact cached response without replaying paid work,
fits or committed statistics. Unknown local work is refused. Laboratory and Paper
share custody/launch infrastructure while retaining separate scientific engines.

## Live engineering pilot

The [frozen eight-case pilot](EXPLICIT_STATE_DATA_TO_PAPER_PILOT_V1.json) assigns
P100-002/017/043/051/054/068/087/090, retaining all 24 nomination slots and two
unsupported wide-input cases. It runs only previously exposed train/dev data,
with fresh probes for all four exact profiles and at most four workers. Its
maximum additional allocation is CNY80 within the existing CNY3000 ledger; that
is an envelope, not reported spend. The [verified execution review](EXPLICIT_STATE_DATA_TO_PAPER_PILOT_V1_REVIEW.md)
retains six incomplete plan-schema outcomes and two unsupported cases, with zero
fits and nominations. It cost CNY0.458912 in 48.018575 seconds. A separately
versioned response-contract revision is required before interactive enablement.
Its completion does not authorize primary ranking or independent discovery.

The [v2 response-format revision](EXPLICIT_STATE_DATA_TO_PAPER_V2.md) has its own
worker and request identities. It leaves this v1 algorithm and all six failed
planning responses intact; no permissive unwrapping is introduced.

The verified v2 pilot and current separate interactive v2 selector are described
in [the v2 review](EXPLICIT_STATE_DATA_TO_PAPER_PILOT_V2_REVIEW.md). This v1
entry remains historical; its failed attempts are never upgraded in place.
