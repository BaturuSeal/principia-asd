# CARBCOMN slag-mixture penetration: native reconstruction and scope

Reviewed 13 October 2026 (Shanghai). P100-055 remains a retrospective research candidate. Native reconstruction does not authorize publication or establish scientific validity.

## Sources and identity

The scenario registry resolves this case to the CARBCOMN record, Zenodo version **17092152** (DOI `10.5281/zenodo.17092152`). All six original source assets are hash-bound by `configs/preparation/P100-055.raw-v1.json`. The new independent parser uses the `Slow penetration_Normal Force` worksheet of `08.2025_Rheology tests.xlsx`. It does not join unrelated numeric folder identities or execute source code. The other response workbooks remain excluded.

The local methods document `08.2025_CARBCOMN Dataset_Early-research results.pdf` was read across all seven pages; pages 1, 4 and 7 were also visually checked. Its SHA-256 is `23fc7b9716e5e0216f158463771c781dab6f95160c3fe0b6277cf5a91dbf07dd`. These observations use the immutable local document, not a claim about subsequently revised online terms.

## What is actually measured

There are nine mixture labels, two ages (immediately after mixing and 30 minutes later), two batch labels per age and 600 successive measurements per trace: **36 traces and 21,600 individual normal-force values**. The force header specifies N. Page 4 describes NF1/NF2 as different batches of the same mixture and describes penetration at a constant 5 µm/s. It does not independently identify specimens or establish whether age-specific batch labels are the same physical batches.

The worksheet labels the clock only `time`, with values 1–600. The frozen task correctly describes `time_s` as a native index with unspecified units. The parser retains that historical field name without converting it to seconds, deriving displacement, or inferring a physical response rate.

Only label-encoded mixture ratios, age and clock index are predictors. NF0/NF30 average columns, derived yield stresses and other response sheets are excluded. No formulas or cached averages are evaluated. Selected measured cells must be finite stored numbers; missing cells, changed headers, duplicate identities and malformed clocks fail the entire reconstruction instead of shrinking the cohort. Negative values remain intact.

## Grouping and lineage

Every mixture's two ages, both batch labels and all time points remain in one partition: **5 train / 2 dev / 2 test mixtures**, with **12,000 / 4,800 / 4,800 rows**. This is nine grouped formulations, not 21,600 independent experiments. Source-row and force-column mappings are retained through a compact 36-trace inventory. The label `Mix-0.5_035` is an explicitly recorded spelling alias for `0.5_0.35`.

The original public development data and test inputs reproduce with zero numerical differences, exact sample/group identity and unchanged partitions. No evaluator-vault outputs are read. Native source force is curator-only; reconstructed test exports contain inputs only. The recipe performs no fitting or learned preprocessing.

## Unresolved admission findings

- **Rights conflict:** page 1 of the methods document states CC BY-NC-SA 4.0. The bound repository metadata and inherited scenario manifest state CC BY 4.0. The new draft records both and remains unauthorized for redistribution; it does not select whichever statement is more permissive.
- **Source quality flag:** merged cell AA604:AF607 says `Incomplete` beneath mixture `0.7_0.30`, spanning both ages and batches. Its meaning is not explained. All 2,400 affected historical rows remain present with an explicit flag; numerical completeness of cells does not resolve scientific completeness.
- **Formulation provenance:** the page-7 appendix lists eight mixtures, omitting workbook mixture `1.0_0.25`. That ninth mixture remains in the historical cohort while its provenance requires clarification.
- **Scientific scope:** admixture dosages and effective versus total water vary in the appendix. Two label ratios do not constitute a full causal formulation specification. Clock units, physical batch independence, measurement uncertainty and valid perturbations remain unresolved.

The exact-contract advisory is display-only. It cannot change evaluation, method selection, numerical ranking or the 520-attempt denominator. Historical outcomes and all unfavorable evidence remain preserved. Any future scientific correction needs a new reviewed edition and frozen comparison.

## Reproduction

Use the native recipe with a new destination outside the three upload roots. `docs/NATIVE_SLAG_VERIFICATION.json` records the formal isolated installed-wheel replay, source bindings, historical parity and all admission blockers. The private draft and exact reader snapshot are retained under `reconstruction-candidates/native-slag-v1`; they are not copied into the frozen scenario edition.
