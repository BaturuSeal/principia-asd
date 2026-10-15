# Risk-choice identity and ordering review

P100-089 is a **historical diagnostic reconstruction with unresolved participant identity and trial chronology**. Reproducing the existing inputs does not verify their asserted strict prior-choice window. No historical rows, rules, scores or denominators are changed.

## Source and complete cohort

The locally registered Zenodo record 15412216 supplies `raw data.csv`: **27,667 rows**, **55 source Subject IDs**, and **165 Subject/Protocol series**. Its two registered assets, including the retained source metadata, are bound by SHA-256 in `configs/preparation/P100-089.raw-v1.json`. No download, evaluator-vault read, fitting or model call is needed.

The native reader reproduces all **17,448 train / 4,211 dev / 6,008 test-input rows**, with **35 / 8 / 12 whole source IDs** and unchanged sample identities. Historical public-data parity has zero numerical differences. Inputs are the declared reward/probability, child-age and protocol indicators, trial progress, preceding-sequence choice and preceding-sequence mean. The first choice has the declared 0.5 history prior. `Hidden`, `EV`, sex, and the current or later sequence-position choices are not prediction inputs. The reader never exports test targets.

Source IDs and each protocol remain together. History follows the old ordering `(Session, Block, Trial, source CSV row)` within each Subject/Protocol. Source row makes the computation reproducible; it is not an acquisition timestamp. Earlier held-out choices can become subsequent inputs under the historical conditional-history task. This is not a free-running simulation or an independent private-test claim.

## Admission defect

The [immutable audit receipt](data-reviews/P100-089-identity-order-audit-v1.json) records:

| Source observation | Count |
|---|---:|
| Repeated Subject/Protocol/Session/Block/Trial keys | 1,765 |
| Extra rows beyond the first at those keys | 1,766 |
| Repeated keys with conflicting choices | 833 |
| Repeated keys with conflicting ages | 10 |
| Repeated keys with conflicting sex codes | 50 |
| Exact repeated source rows beyond the first | 34 |
| Subject IDs with more than one age | 2 |
| Subject IDs with more than one sex code | 5 |

There are **1,085 train / 301 dev / 379 test** repeated order keys. Most are in E1.2 (1,764); one is in E1.1. The CSV contains E1.1, E1.2 and E2.2. Its source description also mentions E2.1, but no rows have that identifier. The reader reports the available protocols rather than inventing missing observations.

A repeated age alone could reflect a longitudinal participant; repeated ordering fields could reflect an unrecorded visit or counter reset. These possibilities cannot be resolved from the file. Demographic conflicts and missing visit/acquisition identifiers therefore require source clarification. The implementation **does not invent new people, infer dates, deduplicate, merge responses or delete unfavorable observations**. It reproduces the historical sequence and preserves every ambiguity.

The group-separation check proves only that the same source Subject ID does not cross partitions. It does not independently establish physical participant identity, and the order audit does not establish that a tied response was available before its successor. In particular, `scientific_split_check.valid = true` is compatible with `native_choice_validation.status = preparation_defect` and `strict_prior_history_verified = false`.

A new versioned contract must specify verified participant/visit identities and observation availability, or explicitly adopt a justified task without unverified history. It needs its own admission review and frozen comparison. Historical scores must not be relabeled as results of that correction.

## Reproduction and visibility

The [installed-wheel replay receipt](NATIVE_CHOICES_VERIFICATION.json) binds the recipe, exact reader/runtime, full cohort and byte-identical regenerated artifacts. The private `reconstruction-candidates/native-choices-v1/P100-089` draft retains each source row, the ordered series inventory and all tied-key coordinates. The full private draft is **8,229,469 bytes expanded** (5,819,323 on disk). Its compact lineage uses shared series references rather than repeating complete histories. No fitted state is hidden behind these references.

Discovery, the affected task leaderboard, Rule Cards and release status show a warning bound to this exact contract and public input hashes. Static HTML carries the same warning. Numerical JSON/CSV records remain unchanged. Tests cover source guards, invalid measurements, future sequence-position independence, protocol reset, duplicate retention, identity conflicts and the separation between reproducibility and scientific admission.

This is the tenth private native draft; no scenario is newly admitted. Thirty remaining compact scenarios need source-specific review and portable reconstruction. Source rights, notice packaging, protocol/units, scientific perturbations and separate scientific review remain open.
