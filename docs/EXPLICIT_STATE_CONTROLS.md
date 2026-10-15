# Fixed controls with explicit learned state

`fixed-controls-explicit-state-v1-dev` is a separate development protocol. It does not replace any historical control or enter the v5 ranking. Its Python API is `principia_asd.engine.bound_controls.BoundControl`. A dedicated macOS worker and separate preparation/run/resume CLI are now available. A new frozen comparison and user-interface integration remain pending; the app continues to offer its existing methods and explicit-state Engine protocols.

## Fixed search specifications

| Control | Executed search | Compatibility |
| --- | --- | --- |
| `fitted_constant` | One intercept fitted by the shared solver | 1–8 inputs; no input statistics used |
| `affine` | One full affine basis of train-standardized inputs | 1–7 inputs, at most eight fitted coefficients |
| `quadratic` | One full degree-two basis, including every pairwise interaction | 1–2 inputs, at most eight fitted coefficients |
| `fixed_symbolic` | Fitted constant; full affine basis when there are 2–7 inputs; then single-input identity, square, tanh and absolute-value bases, in that order | 1–8 inputs; every input's identity term precedes nonlinear terms |

The complete ordered plan is frozen in the configuration before fitting. The scheduled prefix is bounded by the fit and structure caps; every excluded specification is retained as `capacity_excluded_plan`. Lower caps can exclude input-specific structures, visibly in that plan. Input order is the contract's order and can affect which later structures fit within the budget. This is a limited fixed library, not an exhaustive symbolic regression method. Full affine and quadratic controls never silently drop features or interactions to fit their parameter limit.

Every structure uses a fixed initializer: intercept 1, slopes 0. The numerical host is the same `BoundSearch` as the explicit-state Engine: SciPy trust-region least squares on standardized train residuals, or log residuals for `log_mae`, followed by the task's declared development loss. **The fitted constant is not universally a mean/median baseline**: in particular, squared-residual fitting is not a median optimizer for MAE. Existing classical controls remain separately named and unchanged.

Train mean and population standard deviation are computed only for scheduled inputs, with source hashes and scalar identities. A zero-variance input rejects the affected structure; full bases are not silently reduced. Expanded preprocessing operations and both statistics count in simplicity. All final coefficients bind to host fit receipts. No custom kernel, lookup state or numeric literal hides learned values.

## Budgets, selection and failures

Default ceilings match the Engine's numerical envelope: 16 fits, 8,000 structures, 4,096 optimizer residual calls including finite differences, and 2,400 seconds. Controls make zero model requests. These ceilings do not imply equal actual compute: a one-fit control remains a one-fit control, and actual counts are recorded. The in-process API alone does not enforce OS resource limits. The dedicated worker enforces one numerical thread, the shared four-worker semaphore, a 4 GiB RSS watchdog and wall time including slot waiting. Its original journal clock continues through downtime.

All controls use the shared development Pareto selector over dev loss, expanded operations and learned scalar count, with three fixed nomination slots. Repeated structures are deduplicated. One-rule controls retain two unfilled slots. Selection never revises the fixed grammar. Frozen results have separate execution, candidate validity and nomination states; a completed search is not scientific success. Failed fits and normalization rejections remain in the record. Unsupported input dimensions preserve three empty slots and zero fits. Resource exhaustion or an unexecuted scheduled structure makes execution incomplete; cancellation retains completed work.

`DurableBoundRun` binds the configuration, context, runtime and an explicit `provider: none` receipt. Each local operation has an append-only intent/commit boundary. Committed fits are restored without repeated work. An interrupted, uncommitted local operation remains `recovery_required` because its numerical usage is unknown. Resuming it does not reset the budget or repeat the fit.

`evaluate_bound_nominations` accepts the distinct control policy only with the trusted result and nomination hashes. Assessment makes no fits or API calls, keeps all three slots and execution status, and remains excluded from historical/public ranking. Scientific review is `not_assessed`.

## Reproducible engineering check

Install the wheel in a separate verification environment, then run:

```sh
/path/to/verification/bin/python -I scripts/verify_bound_controls.py \
  --workspace /private/path/engineering-fixtures \
  --receipt /private/path/new-control-proof.json
```

This uses two synthetic data generators and all four controls, freezes all eight results before synthetic confirmation assessment, verifies zero-fit reassessment, and tests two hard-exit/resume boundaries. It is an engineering fixture, not a benchmark cohort or independent scientific result. The release copy of the proof is `docs/BOUND_CONTROLS_VERIFICATION.json`.

## Dedicated worker and frozen custody

Preparation copies only the public contract and train/dev files into a new private `control-runs/control-...` directory. It checks exact permitted columns, scenario identity, group/sample separation and numeric values. Test files are not opened or copied. Unknown columns are rejected, not silently dropped. Every input is content-hashed, and later changes to the original source do not affect the prepared job. Workspace placement must be separate from all three upload roots and evaluator custody.

The job pins a source-only runtime snapshot, interpreter hash, dependency versions, configuration, input manifest and macOS sandbox profile before execution. Settings, credentials, provider capabilities and API ledgers are not copied. The child receives an allowlisted environment and no credential variables. Initial execution and resume invoke the same copied worker. Source, input, environment or configuration mismatch blocks dispatch. A live prior worker or competing launcher prevents duplicate dispatch.

The sandbox permits reads of staged inputs, copied source and Python dependencies, with writes only to the job's mutable artifacts and shared semaphore. It denies network access, process forks, sibling scenarios, evaluator/credential canaries, source writes and changes to the staged inputs or launch records. Unsupported platforms fail explicitly; there is no unconstrained fallback. This boundary executes host-authored controls and the expression DSL, not arbitrary generated Python. The installed verification is recorded in `docs/CONTROL_WORKER_VERIFICATION.json`; it includes two recovered committed boundaries and one blocked uncommitted boundary.

With the package installed in a separate environment:

```sh
python -m principia_asd.control_jobs prepare \
  --settings /private/path/settings.json \
  --project-root /path/to/principia-asd \
  --scenario /path/to/data/scenarios/SCENARIO_ID \
  --control fixed_symbolic
python -m principia_asd.control_jobs run /private/path/control-runs/RETURNED_ID
python -m principia_asd.control_jobs resume /private/path/control-runs/RETURNED_ID
```

The saved result contains the original three nomination slots and all executed numerical work. Completed results are verified and returned without a new process. A recovery command never refits an interrupted, uncommitted local operation. Use a new identity for a deliberately new attempt. These records have no private-test evaluation or public leaderboard export.

Before a scientific comparison, freeze the shared envelopes and exact method versions, verify cohort preparation, validate relevant adapters under the same state-accounting policy, and retain every assigned outcome. None of the existing 520 primary attempts or 693 rules is altered by this work.

The separate [eight-scenario control pilot](EXPLICIT_STATE_CONTROL_PILOT_V1.md) assigns all four methods to every scenario, preserves96 fixed nomination slots, and records no private-test assessment. Its source-bound cohort driver supports prepare/launch/status/verify without a provider or automatic replay of unresolved work.
