# P100-015: SHED respondent custody and source imputation

This is a private native reconstruction and scope audit. It does not admit a new scenario, change the frozen edition or authorize redistribution. All historical outcomes, scores and denominators remain unchanged.

## Source and field definitions

The registered source is the Federal Reserve 2025 Survey of Household Economics and Decisionmaking public-use release, updated July 2026 and retrieved 23 August 2026. The exact CSV archive and matching codebook are bound by SHA-256 in `configs/preparation/P100-015.raw-v1.json`. The source DOI is `10.17016/datasets.002`; the data must be attributed to the Board of Governors of the Federal Reserve System. Final notice and rights review remains pending; provenance is not a blanket redistribution approval.

The local codebook's opening pages describe an Ipsos KnowledgePanel survey and distinguish single-year sample/population weights from panel weights. Demographic profile variables were collected separately from the SHED questions. The native file has 12,934 respondents, 815 distinct columns and field dates 17–28 October 2025. Its public-use processing already occurred; these are not raw interviews.

- `EF3_h` asks whether the respondent could not pay a hypothetical USD 400 expense at that time (codebook page 84). It is a stated response, not an observed future default or experiment.
- `D1A` asks about any work for pay or profit last month (pages 18–19). The historical `shock` input is its No indicator. It is not a measured job loss, unemployment spell or exogenous shock.
- `ppinc7` is household income in seven brackets (page 100). Fixed proxies are 5, 17.5, 37.5, 62.5, 87.5, 125 and 175 thousand USD/year. In particular, the open-ended upper bracket does not measure income of USD 175,000; that value is a modeling convention. It was not fitted on train or test.
- `ppage` and `pphhsize` are source demographic age and household size (pages 97–99); synchronized measurement with the expense answer is not established.

## Exact reconstruction and whole-state allocation

The bounded standard-library reader verifies the single registered `public2025.csv` member, record widths and physical line boundaries, unique nine-digit respondent IDs, known categories, state labels, finite numeric values and acquisition dates. All archive bytes and codebook bytes are hashed before decoding. Unsafe paths, duplicate members, unsupported compression, excessive sizes, duplicate IDs and unknown categories fail explicitly.

All **12,934 records** satisfy the historical eligibility rule; **zero exclusions** occur. Source-wide state identity is established before eligibility, then the original hash selects ten confirmation states. Registered train/dev assignments preserve complete states and sample identities:

| Partition | Respondents | State groups |
|---|---:|---:|
| Train | 9,434 | 33 |
| Dev | 1,285 | 8 |
| Test inputs | 2,215 | 10 |

Every permitted measurement and public development target reconstructs with zero numerical differences. Respondent identities are unique and no state crosses partitions. This does not prove independent households, survey clusters or national populations; source sampling and economic environments remain shared. No time-held-out or new prospective observation is involved.

## Upstream imputation is retained and disclosed

The codebook page 117 defines each `*_iflag` as an imputation indicator. The source contains the following flags among the retained respondents:

| Partition | `EF3_h` target imputed | `D1A` work input imputed |
|---|---:|---:|
| Train | 60 | 3 |
| Dev | 13 | 0 |
| Test | 12 | 0 |
| Total | 85 | 3 |

These rows remain in all historical cohorts. The audit does not select, revise or refit based on their outcomes. Individual flags are not predictors or exported lineage; aggregate counts document source quality. No new imputation or fitted preprocessing occurs in this reconstruction.

The source imputer's donor/model state and fitting population are not supplied by this package. Cross-partition independence of imputed answers cannot be claimed merely because respondent/state IDs are separate. The review does not assert that leakage has been proved; it records the unresolved dependency. Demographic profile provenance and other upstream transformations likewise need review before stronger claims.

## Weighting, interpretation and evaluation limits

The 2,749 distinct positive sample weights range from 0.3319 to 3.4882. They determine historical eligibility but are absent from the compact predictors and current evaluator. Compact scoring averages unweighted Brier losses within states and gives each state equal aggregation weight. The older task's `sample_weight` policy remains historical metadata, not an executed compact scoring rule. Current results therefore do not establish weighted legacy parity, population estimates or design-based uncertainty.

The defensible scope is retrospective predictive association with the source's hypothetical expense answer. Causal income effects, future financial distress and practical decision validity are not assessed. The generic perturbation diagnostic also does not establish a scientific error model for bracket proxies or binary work status. Historical complexity counts rules relative to prepared inputs and excludes upstream source imputation and survey processing.

## Custody and verification

The curator reads the registered source snapshot, never the protected evaluator vault. The private output contains only permitted train/dev measurements and test inputs, immutable recipe/runtime bindings, compact native row lineage and an executable preparation script. It emits no individual survey weights, imputation flags, unselected financial/demographic answers or test targets. Raw archives remain unchanged outside the upload roots.

See `NATIVE_SHED_VERIFICATION.json` for exact cohort and isolated installed-package replay, and `SHED_UI_VERIFICATION.json` for the visible scope advisory. The draft is not automatically a new edition admission. Rights/notices, upstream processing and a reviewed scientific/weighting contract remain open gates.

## Separate Engine complexity defect

The browser review also confirmed that Engine rule 3 embeds three coefficients from an earlier executed fit while reporting only its two final-stage parameters. This is distinct from source preprocessing and survey imputation. See [the lineage review](COMPLEXITY_LINEAGE_REVIEW.md) and its hash-bound witness. Historical scores and artifacts are unchanged; the defect is disclosed, not resolved.
