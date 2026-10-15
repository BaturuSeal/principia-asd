# Explicit-state Agent Laboratory development pilot

The frozen pilot finished in **288.56 seconds**, including four exact-profile probes. All eight assignments and all24 nomination slots are retained. This is engineering evidence on previously exposed train/dev cohorts; no private-test evaluation, scientific review or ranking was performed.

| Scenario | Execution | Nominations / slots | Fits | Optimizer evaluations | Retained limitation |
|---|---|---:|---:|---:|---|
| P100-002 | unsupported | 0/3 | 0 | 0 | Outside the one-to-eight-input contract |
| P100-017 | incomplete_method_execution | 1/3 | 2 | 461 | Critique omitted experiment_ids |
| P100-043 | complete | 1/3 | 2 | 413 | One optimizer failure retained |
| P100-051 | complete | 2/3 | 2 | 118 | Execution conformance only |
| P100-054 | incomplete_method_execution | 2/3 | 2 | 158 | Critique omitted experiment_ids |
| P100-068 | failed | 2/3 | 2 | 104 | Provider output truncated; no automatic repair request |
| P100-087 | unsupported | 0/3 | 0 | 0 | Outside the one-to-eight-input contract |
| P100-090 | complete | 2/3 | 2 | 141 | Execution conformance only |

Totals: **3 complete,2 incomplete,1 failed,2 unsupported;10 nominations/24 slots;12 fits and1,395 optimizer evaluations**, with two nonconverged fits retained. The constant three-slot denominator is not reduced for unsupported cases or this two-experiment method.

**40 provider requests** (four probes plus36 inquiry calls) settled, accounting for **CNY2.0091125**. There is no pending or unknown usage in this cohort. The global ledger retains four older unknown reservations; no ambiguous or completed request was repeated.

The verifier ran with the original frozen interpreter and copied source. It checked all input/configuration/runtime bindings, checkpoint chains, expanded candidate states, all36 reconstructed request payloads, response hashes and four probe receipts. Network calls, process dispatch and fitting were denied during verification. Reading terminal records again left the global request ledger unchanged. An initial verifier invocation from the separate installation environment was correctly refused by the frozen environment guard; the campaign environment was not altered.

P100-017 and054 performed two experiments but failed the critique contract because the model omitted the required experiment reference. P100-017 and043 retain failed second fits. P100-068 froze its two nominations before a truncated final report caused failed execution; the paid response and partial evidence remain inspectable. No repairs or new attempts were launched from these observations.

The protocol may be used as an explicitly labelled development option, with its frozen limits and known failure behavior. This does not authorize scientific claims or replacement of the primary comparison. Any later protocol repair must have a new revision and preregistered cohort; completed runs remain immutable.

See [machine-readable verification](EXPLICIT_STATE_LABORATORY_PILOT_V1_VERIFICATION.json), [all assignments](EXPLICIT_STATE_LABORATORY_PILOT_V1_VERIFICATION.csv), [preregistration](EXPLICIT_STATE_LABORATORY_PILOT_V1.json), and [method documentation](EXPLICIT_STATE_LABORATORY.md).
