# Public-goods experiment: participant and observation-window review

P100-087 now has a portable native reconstruction from the registered threshold-game workbook. It reproduces the historical conditional prediction task, without changing any observations, partitions, model submissions or scores. This is curator work; the source includes historically public responses and must remain outside discovery-worker access.

## Source identity and canonical observations

The locally retained Zenodo record **16918146** documents five treatments and two successive experimental sessions. Its `ThresholdPGG_ExperimentalData.xlsx` contains ten sheets: Type1 and Type2 for each treatment. Participants remain in fixed interacting pairs for 20 rounds in session 1, then change partners and reverse roles in session 2. Surveys are answered only after both sessions. The source description contains one contradictory sentence calling the final two rows “Session 1”; the surrounding session definitions and row-role descriptions identify them as session 2. The reader excludes those rows completely.

Only the first two rows of each four-row block in a Type1 sheet define canonical session-1 observations. The reader verifies the corresponding Type2 participant ID, reciprocal partner ID and **all 40 mirrored contributions per pair**. Mirror sheets are consistency evidence and never add samples. Treatment-qualified identifiers distinguish anonymous participants across sheets; the source states each participant belongs to one treatment. Wider recruitment/site dependence remains unassessed.

| Treatment | First-session pairs | Participants | Role 1 / role 2 endowment | Productivity | Threshold |
|---|---:|---:|---|---|---:|
| Full equality | 55 | 110 | 24 / 24 | 1 / 1 | 24 |
| Endowment inequality | 59 | 118 | 36 / 12 | 1 / 1 | 24 |
| Productivity inequality | 56 | 112 | 24 / 24 | 3 / 1 | 48 |
| Aligned inequality | 52 | 104 | 36 / 12 | 3 / 1 | 60 |
| Misaligned inequality | 55 | 110 | 36 / 12 | 1 / 3 | 36 |

The **277 pairs / 554 participants** contribute **11,080 canonical measurements**, with another 11,080 matching mirrored cells checked. All are stored integer actions within the declared endowment. Zero and maximum contributions are retained. Formula cells, missing measurements, nonfinite values, unexpected round headers, incomplete row blocks and nonreciprocal or repeated participants are errors.

The parameter arrays and thresholds match the registered `code_thresholdPGG.zip` source's `ThresholdPGG_CreateDataIntrospection.m`. That code is read as provenance, never executed or copied into the package. Experimental-token units are inherited from the historical contract; protocol/currency conversion and final rights review remain open. Source metadata records CC BY 4.0, which does not by itself close notice and redistribution checks.

## Permitted history and exact partitions

For each player, rounds **3–20** are prediction targets. Inputs include strictly earlier own/peer contributions, their expanded prefix means, fixed endowment/productivity parameters and the announced threshold. The previous-success indicator and required-contribution calculation expand directly from those earlier observations and parameters. They are deterministic measurements/transforms, not fitted state.

First and second rounds provide history only. A target at round `r` uses no response from round `r` or later. Exact source sheet, player/peer rows, target column, lag-two column and inclusive history-column range remain in each row's lineage. Post-session surveys in W:Z, all session-2 observations, linear/four-player game files and simulated or fitted results are excluded.

This is **one-step online conditioning**: after an earlier held-out round occurs, its observed response may appear in a later test input. This permission is explicit in the frozen historical contract. Test inputs therefore are not a permanently secret-output dataset; later histories can encode earlier responses. The task does not test free-running multi-step behavior, de novo participant prediction or independent scientific discovery. A future sequential deployment would also need to enforce the same observation window operationally.

Every pair, its two players and all its selected rounds stay together. The original per-treatment test reservation and compact-v2 development allocation reconstruct exactly:

| Partition | Pairs | Selected rows |
|---|---:|---:|
| Train | 178 | 6,408 |
| Dev | 44 | 1,584 |
| Test inputs | 55 | 1,980 |
| Total | 277 | 9,972 |

The compact edition uses a single whole-pair dev split; the older preparation's five-fold designation is provenance, not five folds executed by this campaign. All sample IDs, group IDs, allowed inputs, development targets and split membership reproduce with **zero numerical differences**. Pair separation does not establish independence of treatment populations or recruitment environments, nor does predictive accuracy identify a causal explanation for cooperation.

## Verification and admission boundary

The [installed-wheel replay receipt](NATIVE_GAMES_VERIFICATION.json) binds three source assets, exact reader modules, the canonical/mirrored measurement counts and byte-identical replay of every generated artifact. Private drafts and reader snapshots live under `reconstruction-candidates/native-games-v1`; neither the frozen edition nor its evaluations were replaced. The complete private draft occupies **5,325,789 bytes expanded** (4,265,734 on disk), including source lineage and replay metadata, below the default 10 MB size limit. This size check does not grant scientific or rights admission.

Twenty-one new synthetic tests exercise reciprocal participants, mirrored measurement equality, fixed whole-pair allocation, source action bounds, explicit prior-round history, future terminal-response independence, excluded session/survey perturbations, formula rejection, bad headers and external worksheet relationships. Changing a prior held-out response correctly changes only later prediction inputs. This is a stronger timing test than incorrectly requiring all test inputs to remain invariant to every held-out response.

This is the **ninth private native draft recipe**. The frozen 40-case edition still has no embedded executable preparation scripts, and **31 scenarios** remain to receive this source-specific review and reconstruction. Full contract validity, scientific perturbation standards, rights/notices and separate scientific review remain open. No new scenario is admitted by this work.
