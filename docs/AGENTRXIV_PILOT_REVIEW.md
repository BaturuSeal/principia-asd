# AgentRxiv archive pilot: verified engineering outcome

The preregistered `agentrxiv-archive-pilot-v1` ran on eight engineering-exposed scenarios from **19:51:41 to 20:02:15 UTC on 11 October 2026** (10 minutes 34 seconds). All eight assignments are terminal: **six complete, two incomplete, no transport failures**. Completed attempts contribute **18 valid rule assessments**. These results remain separate from the 520-attempt primary ranking.

All eight attempts completed two initial laboratory cycles, published their reports and retrieved a peer report. Six also passed the exact peer-reference, executed extension, structural revision and reporting guards. The two incomplete outcomes are preserved:

| Scenario | Execution boundary | Consequence |
|---|---|---|
| P100-051 | Follow-up critique transcribed the peer report ID incorrectly: `report-0dc28de6713326573` instead of `report-0dc28de671326573` | Computed follow-ups remain recorded; exact evidence binding fails, so no ranked rule |
| P100-090 | The donor expression used all eight free parameters; two proposed extensions introduced disallowed `p8`/`p9` | Both follow-ups fail legality checks; no valid cross-laboratory experiment or structural revision, so no ranked rule |

P100-017 also retained an initially invalid development expression before a valid revision. These are engineering observations from development data and conformance events. Test losses were not used to revise prompts or select follow-up execution. There is no automatic success-seeking rerun.

The whole cohort submission freeze preceded assessment. [Offline verification](../leaderboards/receipts/agentrxiv-archive-pilot-v1-verification.json) replayed **144 recorded responses and all eight assessments** using the exact copied runtime `8ee0c73aa0f401ce0f91404af0b55d12c0ae5d24f034be47ebe97adcafb47a89`. Request payloads, handoffs, programs, archive contents and conformance outcomes matched exactly, with zero API calls and no ledger mutation.

The pilot cost **CNY 5.340137**. Global conservative accounting afterward was **CNY 52.440975 / 3,000**: CNY 28.440975 recorded usage plus CNY 24 unresolved historical reservations, with no pending calls. All 144 new calls have recorded usage. Existing ambiguous calls were not replayed or released.

The actual completed P100-043 archive was checked in the browser: two laboratories, three published reports, a foreign-report retrieval, expanded donor formula and parameters, two follow-up computations and downloadable run records. Console errors: zero. Screenshot: [archive view](images/agentrxiv-archive.png). The UI labels model prose as unreviewed and exposes host-checked evidence separately.

This pilot establishes execution and record integrity for the constrained adaptation. Peer reuse is not independent corroboration; one eligible foreign report cannot establish retrieval effectiveness. It does not establish a benefit over other methods, novelty or scientific validity. See the [method card](method-cards/agentrxiv.md) for the full adaptation boundary.
