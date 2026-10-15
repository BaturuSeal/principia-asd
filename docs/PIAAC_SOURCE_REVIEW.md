# P100-039: respondent custody and earnings-decile scope

This is a private reconstruction and scientific-scope review, not admission of a new scenario or authorization to redistribute OECD data. The frozen 40-scenario edition, all submissions and quantitative assessments remain unchanged.

## Source and measurement identity

The registered source is OECD PIAAC Cycle 2, December 2024 public-use release, collected September 2022–August 2023 and acquired locally on 14 September 2026. The registry-aligned `39_sociology_oecd_piaac` projection supplies complete USA and Japan CSVs plus the official international XLSX and derived-variable PDF codebooks. File sizes, SHA-256 hashes and roles are in `configs/preparation/P100-039.raw-v1.json`. Native source files are not bundled with the draft.

The international codebook's PUF sheet identifies `SEQID` as a randomly derived sequential identifier (row 2), `AGEG5LFS` as derived five-year age groups (2124), `YRSQUALC2` as years assigned from highest completed education (2197), `EARNHRDCLC2` as hourly earnings excluding bonuses for wage and salary earners in deciles (2318), and `SPFWT0` as final full sample weight (2404). The derived-variable codebook page 43 confirms ages 25–29 through 60–65. The final bin's fixed midpoint is 62.5; these are not measured exact ages. The target is the existing indicator `EARNHRDCLC2 >= 8`, not absolute PPP earnings. The old native parser's eligibility prose referred to PPP wages; that prose is not a measurement definition.

## Complete cohort and separation

| Source | All records | Eligible | Excluded |
|---|---:|---:|---:|
| USA | 3,765 | 1,813 | 1,952 |
| Japan | 5,165 | 3,477 | 1,688 |
| Total | 8,930 | 5,290 | 3,640 |

Eligibility preserves age groups 3–10, education 0–30, known deciles 1–10 and positive final weight. Reasons are nonexclusive and missing-value codes remain inventoried. No missing target is imputed; younger respondents, missing/valid-skip earnings and unavailable education remain outside the historical cohort. Selection is conditional on observed earnings and does not represent all adults.

The source decoder checks 2,483 distinct columns, complete one-line semicolon records, canonical nonduplicated respondent IDs, both country-code fields, numeric domains and finite values. It rejects unrecognized missing codes, changed schema/units, duplicate identities and unsafe sizes. It retains only the necessary fields; plausible values, assessment responses, occupations and other background values never become predictors or exported lineage.

The unchanged fixed hash maps country-prefixed respondent identity into ten blocks per country. Test is buckets 0 and 1; registered development blocks remain intact. Reconstruction reproduces **3,350 train / 886 dev / 1,054 test-input rows** across **13 / 3 / 4 whole blocks**, with zero numeric differences and no respondent overlap. Hash blocks are allocation/aggregation units, not independently sampled survey PSUs. Both countries appear in each partition; this is neither country-held-out nor time-held-out evidence. Household, geographical clustering and survey design variance are not reconstructed.

## Weighting, interpretation and complexity

All eligible final weights are positive and nonconstant: USA 6,892.750611–243,536.148622; Japan 5,009.305005–38,671.696887. The historical native task retained `sample_weight`, while the compact task exports only education, age and country. Current deterministic scoring is unweighted within each block, then an equal block mean. The task preserves historical weighting as metadata, not an executed scoring rule. Compact Brier results must not be called survey-weighted parity or population estimates. The new reader does not insert weights or rescore existing outcomes.

There are zero fitted preprocessing transforms and zero discovery-rule fits in this reader. Upstream educational derivation, age coarsening, earnings-decile construction and survey weighting already occurred in the public-use source. Their costs and learned states are not represented by historical rule-only complexity. No plausible-value duplication is used. The perturbation diagnostic is not an established measurement-error model for country indicators or categorical age bands.

The supported interpretation is a complete-case contemporaneous predictive association in the two public-use samples. Prospective income, population-level attainment, causal educational returns, mechanisms and independent novelty are not established. A reviewed weighting/estimand contract and appropriate survey design support are required before stronger claims.

## Custody and release gates

`catalog/piaac.py` is curator-only. Its private draft records native file/row coordinates, fixed operations and opaque sample identities. It exports no test targets, final weights, plausible values or unused background values and reads no evaluator vault. Both raw files and two codebooks are hash-bound; the installed reader and dependencies are frozen per draft. Exact replay demonstrates reproducibility, not scientific validity.

The local provenance reports OECD attribution and pass-through obligations, and CC BY 4.0 for the Reader Companion rather than blanket permission for every payload. Local terms-page acquisition was unavailable in the original record. This audit does not resolve final rights, notices or upstream third-party restrictions. Public release remains unauthorized. Verification results are in `NATIVE_PIAAC_VERIFICATION.json`; current numerical rankings remain historical and unchanged.
