# Training trajectories and calibrated transistor sweeps

This review checks P100-043 and P100-051 against registered original measurements, without reading the evaluator vault or using final predictive scores. Both remain retrospective draft candidates. Reconstruction and source-level separation pass within the scopes below; scientific admission and redistribution approval remain pending.

The [portable reconstruction receipt](NATIVE_STRUCTURED_VERIFICATION.json) records source hashes, exact sample coverage, original partition membership and isolated installed-wheel replay. Recipes are in [`configs/preparation`](../configs/preparation/). Raw acquisitions are curator inputs and must not be exposed to discovery agents.

## P100-043: Gemstones training trajectories

The reader consumes the registered `wandb_df_raw.jsonl`, retaining 22 hot training histories (`pretrain=true`, `cooldown=false`). Model IDs must agree with the integer width/depth fields. Duplicate architectures, duplicate JSON keys, aliased optimizer-step keys and ambiguous stage flags are rejected. Non-hot histories are excluded with their source line numbers recorded.

For each architecture, two permitted observed checkpoints calibrate the forecast: the latest at or before 10 billion tokens and the latest at or before 20 billion tokens. They must be distinct and precede every response checkpoint, which lies after 20 billion and at or before 100 billion tokens. Tokens equal optimizer steps × 2,048 × 2,048, as specified in the hash-registered extraction code at lines 201–207 and 407. No final-loss summary, global-loss history, cooldown measurement, fitted law or future checkpoint becomes an input. Missing source checkpoints are documented rather than interpolated.

The full architecture is kept within one split: **14 train, 3 dev and 5 test architectures**, with **616 / 125 / 221 rows**. Native identities, all input values, development responses and each partition's membership match the historical compact tables exactly. This supports the declared architecture-separation check; it does not establish independent training corpora, independent validation data or replication across random seeds. Validation-loss units follow the inherited nats/token declaration; the reader does not independently audit the upstream loss implementation.

The task is a calibrated forecast of later observed training losses. It cannot support claims about predicting an entirely unobserved training run, generalizing to a different corpus or discovering a causal scaling law without additional evidence.

## P100-051: transistor characterization

The registered `Figure 2e-Vg sweep of 36 FET.csv` contains one voltage coordinate (`wave0`) and 36 response columns (`wave1`–`wave36`). The coordinate has 201 distinct, increasing points from -20 to +20. Source rows 2, 102 and 202 provide the three disclosed calibration measurements at -20, 0 and +20 V. These rows are excluded from every scored response cohort. Stored current is multiplied by one million under the inherited A-to-uA declaration; no fitted transformation is used.

Every response column stays within one split: **22 train, 5 dev and 9 test columns**, with **4,356 / 990 / 1,782 scored rows**. Native row and column lineage, all numerical values, opaque IDs and original partition membership match exactly. The checks establish complete-column separation. The anonymous headers do **not** establish physical device identity, fabrication-batch independence or units on their own. Those facts require further source documentation before scientific admission; the recipe and reconstruction receipt retain this limitation.

Because the +20 V endpoint is disclosed before reconstruction, this is offline sparse characterization conditional on three measured responses. It is not an uncalibrated device prediction, an online forward sweep forecast or evidence for a mechanism. The broader source response inventory remains outside this task and should be considered separately during scenario redesign.

## Adversarial checks and remaining work

Synthetic tests perturb all undisclosed test responses, later training checkpoints and summary/fitted fields. None changes exported inputs or development measurements. Other fixtures reject duplicate identities, missing early anchors, unexpected columns, formulas, nonfinite measurements, invalid voltage order and incomplete unit assignments. Separate source checks reject changed bytes or hashes. These are engineering guards, not independent scientific validation.

All 8,090 rows across this batch match historical public values with **zero floating-point differences**. Every generated artifact replays byte-identically from the installed wheel. Original scenario files, private test targets, frozen campaigns and numerical leaderboard records remain unchanged. No API calls, fitting attempts or model selection occurred.

Together with P100-012/062, four draft recipes are verified. The frozen edition still lacks its own embedded executable reconstruction scripts. The other 36 cases require native preparation and source-specific review. Admission, source rights and notices, scientifically justified perturbation contracts, corrected-edition comparisons and scientific review remain open. No new scenario is added to the active count by this work.
