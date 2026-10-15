# Fixed-control engineering pilot v1

This preregistered development check covers the same eight previously engineering-exposed scenarios as the explicit-state Engine pilots: P100-002,017,043,051,054,068,087,090. It establishes execution and accounting behavior, not independent scientific performance. Historical scenarios, Engine pilots and primary rankings remain unchanged.

## Frozen assignments

Every scenario receives the four `fixed-controls-explicit-state-v1-dev` methods: `fitted_constant`, `affine`, `quadratic`, `fixed_symbolic`. The denominator is **32 assigned attempts and 96 nomination slots**. All unsupported, failed, incomplete, cancelled and unresolved outcomes remain in the record. A single-rule control can leave two nomination slots empty; these are not automatically execution failures.

Each attempt uses the existing sandboxed worker with the same numerical ceilings as the explicit-state Engine: 16 fits, 8,000 structures, 4,096 optimizer residual evaluations, 2,400 seconds and 4 GiB RSS. At most four workers run concurrently with one numerical thread each. The fixed ordered grammar, supported dimensions, full-basis parameter constraints and train-only normalization are unchanged. Actual work is reported separately; common ceilings do not imply equal compute.

Preparation stages only each contract and its permitted train/dev files. Their hashes, method configurations, source-only runtime, interpreter/dependency configuration and 32 launch identities freeze before any fitting. Discovery does not read evaluator targets. The driver has no provider calls or capability probes; extra API allocation is zero. It records the existing ledger before dispatch and checks it remains unchanged after completion.

## Execution and recovery

The private root is `control-campaigns/explicit-state-controls-pilot-v1`; each job lives under `control-runs/`. A source-bound background driver invokes only the frozen control worker. Exclusive driver/launcher and worker locks prevent duplication. Completed outcomes and submissions are immutable. Interrupted committed work may resume from its journal; uncommitted numerical work stays unresolved and is never automatically refitted. A new deliberate attempt needs a new identity.

All 32 outcome receipts freeze together. The completion verifier checks exact assignment and slot coverage, staged input/runtime bindings, complete checkpoint chains, expanded candidate programs and learned-state references, preserved failures and no ledger changes. It performs no fitting, provider calls or private-test assessment. Compact JSON/CSV exports are development receipts, not additional leaderboard entries.

## Reproduction

With the current wheel installed into a separate environment:

```sh
python -I -m principia_asd.control_pilot prepare /private/settings.json \
  --campaign-id NEW_COHORT_ID --project-root /path/to/project
python -I -m principia_asd.control_pilot launch /private/control-campaigns/NEW_COHORT_ID
python -I -m principia_asd.control_pilot status /private/control-campaigns/NEW_COHORT_ID
python -I -m principia_asd.control_pilot verify /private/control-campaigns/NEW_COHORT_ID
```

Before launch, save the read-only `ledger_snapshot(workspace)` from `scripts/verify_control_pilot.py` as an immutable `ledger-before.json` under the cohort root. The release export uses that script with `--receipt /path/to/new-receipt.json` after execution stops. Do not replace an existing manifest, completed outcome or release receipt. The `launch` command resumes using the manifest's copied driver and returns immediately if already running or complete.

Scientific admission, data corrections, additional method adapters and a new symmetric comparison remain separate release gates. These development results cannot establish novelty, impact or superiority over the Engine.
