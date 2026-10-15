# Explicit-state Engine engineering pilot

This separate development cohort tests the model interface and execution of the
explicit-state Engine. It does not change `full-comparison-v5`, assess private
test outcomes, or enter the public rule ranking. Scientific novelty, impact and
external review remain `not_assessed`.

The fixed assignments are the eight previously engineering-exposed scenarios:
P100-002, P100-017, P100-043, P100-051, P100-054, P100-068, P100-087 and P100-090.
The protocol accepts one to eight inputs. P100-002 (ten inputs) and P100-087
(fourteen) are retained as `unsupported`; no input is silently removed. Each
assignment retains three nomination slots, for a fixed denominator of 24.

GLM-5.3 plans, DeepSeek-V4-Flash codes, Qwen3.8-27B critiques, and Kimi-K2.6
reports. The unchanged two-round protocol freezes its nominations before the
reporter responds. Only contract, train and dev files are staged into private
cohort custody. Every staged file, copied Python runtime, provider profile and
job request is hash-bound before dispatch. No private evaluator is configured.

Four exact-configuration JSON probes must pass before workers start. Existing
probe ledger entries are recovered only from settled cached responses; ambiguous
requests are never sent again. A failed probe blocks the cohort. The existing
global CNY 3,000 ledger is used, with at most CNY 8 for probes and CNY 12 for each
of six executable assignments: **CNY 80 additional maximum**, not a new budget.
Each attempt retains the existing seven-request, sixteen-fit, 4,096 optimizer
evaluation, 40-minute and 4-GiB limits. At most four workers execute at once,
sharing the ordinary worker-slot guard and one numerical thread per worker.

The private runner lives in `principia_asd.bound_pilot`. Preparation, launch and
status use the following interface, with paths supplied by the operator:

```bash
python -m principia_asd.bound_pilot prepare PRIVATE_SETTINGS \
  --campaign-id explicit-state-engineering-pilot-v1 --price-check DATED_PRICE_CHECK
python -m principia_asd.bound_pilot launch PRIVATE_COHORT
python -m principia_asd.bound_pilot status PRIVATE_COHORT
```

Preparation is create-only. Initial launch and safe continuation use the frozen
runtime in the manifest. Do not alter the environment, provider profiles or
inputs. The UI exposes results but cannot launch or resume an assigned cohort
job independently; cancellation remains available. Completed outcomes are never
replayed. Uncommitted numerical work or unknown billing yields an explicit
unresolved record with all three slots retained.

The runner freezes every assigned outcome and writes an execution-completion
receipt. This receipt does not mean that every method completed or that the
research succeeded. The monitor reports this cohort separately from primary
and earlier adapter cohorts. Live conformance findings must be reviewed before
a new protocol revision or symmetric scientific comparison is frozen.
