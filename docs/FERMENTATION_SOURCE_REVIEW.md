# Fermentation acquisition-clock review

P100-086 has a verified **historical diagnostic reconstruction**, with a failed temporal admission check. Exact replay establishes how the existing table was produced; it does not establish a valid six-hour prospective forecasting contract. No historical data, scores, attempts or denominators were changed.

## Source and reconstructed cohort

The registered `EFP_long.csv` from the locally retained Zenodo record 14619074 contains **50,536 observations from 406 production batches**. The reader uses only acquisition timestamp `date`, batch identity `batch_id`, nominal cultivation time `hh` and measured potency `hx`. Physical potency units are undocumented; the implementation does not invent mg/L or U/mL. Source rights, acquisition protocol and notices still require review.

The legacy preparation sorts each batch by the nominal clock, using the original single-key quicksort behavior, then chooses observations six rows before and after each origin only when both nominal time differences equal six. Exact NumPy and reader versions are bound because tie ordering affects historical identity. **138 batches contain repeated nominal clock values**, while their acquisition timestamps are unique and strictly increasing. Tied measurements are retained rather than silently merged. Batch 374 has seven observations and no eligible window; this exclusion is recorded.

All **44,284 eligible rows from 405 batches** reconstruct with zero numerical differences and exact sample/group membership: **28,378 train / 6,774 dev / 9,132 test-input rows**, in **260 / 64 / 81 whole batches**. Inputs are nominal time, current observed potency and the expanded six-hour past difference. This is conditional forecasting from measured potency, not a demonstrated online soft sensor. Other process variables, fitted states and future responses do not become prediction inputs.

## Temporal defects

Every selected past lag is six hours by acquisition timestamp. However, **113 nominal six-hour targets have a different actual horizon**, comprising **71 train, 18 dev and 24 test-input rows**:

| Actual horizon | Rows |
|---|---:|
| 5 h 15 min | 6 |
| 5 h 30 min | 77 |
| 5 h 40 min | 3 |
| 5 h 45 min | 22 |
| 5 h 50 min | 3 |
| 6 h 30 min | 2 |

The other 44,171 rows have exactly six-hour timestamp horizons. The [immutable audit receipt](data-reviews/P100-086-temporal-audit-v1.json) identifies each disagreement by sample ID and exact past/origin/target source rows. It reads no protected evaluator targets and performs no fitting or model calls.

Whole-batch separation holds, but the compact edition's train/dev assignment interleaves calendar time: the earliest dev batch begins on 5 January 2022, while the latest train batch begins on 4 September. The historical test set reserves the latest 81 batch starts. This does not prevent overlapping acquisition windows: the latest train target is **10 September 01:00**, the latest dev target is **7 September 18:00**, and the earliest test origin is **6 September 03:00**. All are source-local timestamps with no recorded timezone. Batch-start ordering alone cannot support a strict prospective validation claim.

These issues require a **new reviewed contract and cohort**, with timestamp-defined target availability, a stated tolerance or interpolation policy if needed, chronological development allocation and appropriate boundary purging. Removing the 113 rows from an already scored cohort would change its denominator and is not permitted. The existing table and all outcomes remain historical diagnostic evidence. No correction has been admitted or compared.

## Replay, visibility and remaining gates

The [installed-wheel replay receipt](NATIVE_FERMENTATION_VERIFICATION.json) binds all three source assets, identities, partitions, exact reader sources and byte-identical replay of every generated artifact. `scientific_split_check` in that receipt checks whole-batch membership only; the separate `temporal_validation.valid` is **false**, with three explicit admission blockers. A passing reconstruction status must not be interpreted as scientific approval.

The private draft under `reconstruction-candidates/native-fermentation-v1` is **20,534,922 bytes expanded** (17,496,673 bytes on disk), largely due to verbose per-row source lineage. It is outside all upload roots and is **not size-admitted**. A compact, lossless lineage representation and a new immutable draft are needed before considering the default 10 MB package limit. No size exception has been granted.

The discovery form, task leaderboard, individual Rule Cards and release status display a warning bound to this exact historical contract and input hashes. Portable HTML carries the same warning. Numerical JSON/CSV records remain unchanged. Synthetic tests cover actual versus nominal clocks, batch overlap, duplicate timestamps, source identity, invalid measurements, retained clock ties, future-response isolation and immutable read-only review.

This is the eighth native draft recipe. **32 remaining compact scenarios** need portable reconstruction and source-specific split review. The frozen 40-case edition still has zero embedded executable preparation scripts. Final contracts, physical units, source rights, task-appropriate perturbations and scientific review remain open. No new scenario admission or scientific discovery claim follows from this work.
