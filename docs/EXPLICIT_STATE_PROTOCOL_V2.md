# Explicit-state protocol v2: interface revision

`principia-explicit-state-protocol-v2-dev` addresses the first live pilot's
interface failures. It inherits the v1 two-round algorithm, fitting code,
kernel legality checks, budgets, four model roles and three-slot development
selection. It does not reinterpret or resume a v1 scientific run as v2.

Each role now receives its exact JSON contract before generation. Planner kernel
objects contain only `name` and `expression`; names match
`^k_[A-Za-z0-9]{1,30}$`. Kernels are parameter-free. The coder declares fitted
coefficients in a separate rule's `initial` map. Extra fields, unknown symbols,
literal state and invalid names still fail validation. This is clearer guidance,
not relaxation of the conformance gate or automatic model-output repair.

The declared `complete-inventory-compact-evidence-v1` context keeps all input
names, state bindings and current kernel definitions. The same predeclared
development selection supplies candidate packets containing exact errors,
residual diagnostics, fitted parameters and expanded complexity counts. A
complete candidate index preserves every retained candidate; every failed
experiment and rejected patch remains represented. Full executable programs,
source artifacts and original failure records remain in host checkpoints and
frozen submissions, linked by hashes.

Repeated full program copies, repeated expanded numerical expressions and
extraneous invalid-patch prose are replaced by declared projections. No candidate
or failure is silently removed to fit a message. This is a compact-packet method,
not an agent-accessible retrieval tool. The unchanged 48,000-byte guard still
fails before dispatch if the complete declared packet is too large. Reporter
packets retain the frozen nomination manifest and candidate/state context.

An offline development check reprojected all 41 provider-boundary contexts from
the frozen first pilot. Maximum size fell from 57,688 to 31,032 bytes, with zero
API calls, zero fitting and an unchanged ledger. See
`BOUND_CONTEXT_V2_VERIFICATION.json`. This demonstrates compatibility with those
saved contexts; it is not proof of live response conformance or arbitrary future
context capacity.

The dedicated worker accepts a distinct `engineering_only_explicit_state_v2`
scope, creates `bound-v2` request identities and uses the original source snapshot
for restart. Cross-version checkpoint recovery is refused. The interactive
**Engine protocol** selector explicitly offers v2 (recommended) and original v1.
The chosen revision appears in history, monitor and downloaded records. Older
API requests and CLI commands that omit a revision retain v1. No primary/private-test
evaluation or leaderboard replacement is authorized by this revision.

For an explicit CLI selection, use:

```sh
principia-asd run --scenario SCENARIO --method principia_engine_explicit \
  --protocol v2 --settings PRIVATE_SETTINGS
```

Resume reads the saved request and original runtime, never the current selector.
Both revisions are refused by legacy `evaluate` and `replay`. Unknown revisions
and protocol options on unrelated methods fail before job creation.

The completed v2 live pilot has six complete and two unsupported outcomes,
with all 24 slots retained. This verifies development execution only. See
[the pilot review](EXPLICIT_STATE_PILOT_V2_REVIEW.md).

The new cohort keeps the same eight development-exposed assignments and 24
nomination slots, including P100-002 and P100-087 as unsupported. A fresh identity
permits new development requests; it does not replay earlier billed requests.
Generation profiles and prices are unchanged. The maximum additional cost is
CNY 80 under the existing CNY 3,000 global cap, including four exact-profile probes.
Use `principia_asd.bound_pilot prepare ... --protocol v2` before launching from
the frozen runtime. A completed execution receipt retains all failures and says
nothing by itself about scientific discovery or comparative performance.
