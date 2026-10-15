# First explicit-state live pilot: execution review

The frozen pilot finished on 13 October 2026 at 12:30:18 UTC after **201.84
seconds**. All eight assigned outcomes and all 24 nomination slots are preserved.
This is an engineering result, not a new leaderboard or scientific comparison.

| Scenario | Execution | Main finding |
|---|---|---|
| P100-002 | Unsupported | Ten inputs exceed the frozen eight-input limit |
| P100-017 | Failed | Context-size guard stopped the protocol after five model requests |
| P100-043 | Complete | Both rounds, accepted kernels and frozen evidence-linked reporting executed |
| P100-051 | Incomplete | All proposed kernels rejected by the naming/state contract |
| P100-054 | Incomplete | All proposed kernels rejected by the naming/schema contract |
| P100-068 | Incomplete | All proposed kernels rejected by the naming/state contract |
| P100-087 | Unsupported | Fourteen inputs exceed the frozen eight-input limit |
| P100-090 | Incomplete | No accepted kernel and one round without a new executed fit |

There are 18 nominated candidates in 24 fixed slots, 32 retained candidates,
35 actual training fits and 650 optimizer evaluations. Nomination does not turn
an incomplete method into a successful one. Only P100-043 passed the complete
method-conformance check. Parameter uncertainty and scientific review remain
unassessed.

All four exact-profile capability probes passed. The pilot made **44 completed
provider requests**, including four probes, for **CNY 2.467353**. No new unknown
or pending charge remains. Total campaign accounting is **CNY 54.908328 / 3,000**,
including four older unknown reservations totaling CNY 24. The offline check
verified every cached response and payload hash against its settled ledger
entry, the frozen input/runtime bindings, all outcome hashes and the fixed
denominator. It made zero model calls and zero fits. See
`EXPLICIT_STATE_PILOT_V1_VERIFICATION.json`.

The dominant failure is an interface problem. There were 20 rejected kernel
names, nine patches with an extra field, and four kernels containing an
undeclared free parameter. The prompt describes the scientific task but does
not state these constraints clearly enough before the first proposal. Valid
JSON transport is therefore insufficient to establish method conformance.
P100-017 also exceeded the protocol's context limit as retained evidence grew;
the guard stopped rather than silently dropping context.

The next development revision should supply the exact kernel schema, naming
grammar, allowed symbols and the distinction between parameter-free kernels
and parameterized rule drafts. Context management needs explicit, source-linked
paging or a declared compact evidence representation, preserving complete local
artifacts and their accounting. Test those changes with these development
failures and synthetic fixtures, then freeze a **new** configuration and identity.
Do not edit, replay, relabel or remove this first pilot. No private-test outcome
has been accessed for this work.

The existing primary comparison remains **520 attempts and 693 rules across 40
scenarios**. Its source, configuration, assessments and ranking are unchanged.
Wider-input support, symmetric explicit-state controls, dimensional/scientific
contracts, rights, source corrections and the remaining adapters are separate
release gates.
