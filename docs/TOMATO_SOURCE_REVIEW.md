# P100-036 stored tomato phenotype and plant-custody review

This is a private reconstruction of the historical diagnostic task. It is not a new acquisition, independently extracted imaging dataset or newly admitted benchmark. Historical rules, metrics, failed attempts and split membership remain unchanged.

## Source identity and reuse

The registry-aligned release projection points to Zenodo record [20638584](https://zenodo.org/records/20638584), DOI `10.5281/zenodo.20638584`, by Giorgia Del Cioppo, Sylvain Poque, Simone Scalabrino, Gabriella Scippa, Kristiina Himanen and Dalila Trupiano. The locally preserved source snapshot declares CC BY 4.0 and a publication date of 11 June 2026. Acquisition metadata spans November 2023–June 2024. These are historically public, retrospective observations.

`configs/preparation/P100-036.raw-v1.json` binds the exact integrated phenotype workbook, metadata workbook and source metadata, plus the historical contract and legacy parser specification. The phenotype and metadata SHA-256 values are `77bcb77f1b003dba22b30ee562a145c9559fcc56c806290151623821d49c2001` and `446f83d4be672267efdd0128b4657a13f5d0599fcaf2e8ccb51a885b6c9d2f41`. The reader independently implements stored-field selection and historical identities. No evaluator, source code, fitted model or old runtime is copied. Final citation/notice packaging and scientific admission remain open; this record is not a redistribution authorization.

## What is actually reconstructed

All **347 stored phenotype rows** join one-to-one to **347 metadata rows**, using exact Plant ID and the source DAS label. All **81 plants** have stable cultivar, treatment and experiment assignments across repeated sampling. The reader checks XML size limits, source identity, exact headers, stored numeric cells, unique coordinates, cultivar consistency, missingness and target/area domains. It rejects formulas in selected cells, hidden measurements, unsafe/external worksheet relationships, merged cells and ambiguous joins. It never executes Excel formulas or follows external links.

Predictors are the stored NPQ_Lss, Rfd_Lss, NGRDI and AREA_MM values plus four categorical indicators derived from known cultivar and treatment. The target is the separately stored QY_max field. Laboratory outcomes, environmental summaries, time labels, future measurements and unused morphological/colour fields are not predictors. There are no missing selected values in this source; the reader records any incomplete row explicitly and never imputes it. No numerical fitting or API calls are needed.

**These are author-derived measurements.** This utility does not reproduce segmentation, instrument calibration, fluorescence reduction or RGB feature extraction. The local raw-image selection contains only Tiny Tim NPQ images; it cannot independently reconstruct both cultivars' complete feature inventory. That image archive is neither read nor bundled by this recipe. Calling the workbook a native source does not make its features raw sensor observations.

The historical AREA_MM unit declaration is preserved exactly; the decoder does not assert a separately validated area calibration. NPQ, Rfd and QY_max can share fluorescence acquisitions and calibration quantities. The available tables do not establish absence of algebraic or shared-source dependence. A dedicated source-formula/extraction review is required before interpreting the task as discovery of an independent physiological relationship.

## Timing and experimental dependence

There are **81 DAG disagreements** between the phenotype and metadata workbooks, all in their initial sampling rows. The first Micro-Tom example records 23 in the phenotype table and 22 in metadata. Both values and their source coordinates remain in curator lineage. Source DAS/DAG definitions also require protocol clarification. Neither age field enters the historical predictor set; this audit does not silently correct them, reinterpret their physical meaning or invent a chronological task.

The two source experiment IDs are **114 (197 rows, Micro-Tom)** and **121 (150 rows, Tiny Tim)**. Cultivar and experiment therefore coincide in this source selection. Whole-plant splits verify **52 train / 13 dev / 16 test plants**, with **220 / 61 / 66 rows**, preserving the original confirmation cohort. Repeated samplings never cross partitions. This does not establish independent-experiment, new-cultivar, site or season transfer. Metadata's measurement dates are checked as stored values but are not used to invent time-zone or causal-order assumptions.

The defensible historical scope is contemporaneous prediction from prepared imaging descriptors under known treatment. It does not demonstrate early stress forecasting, treatment causality, independent biomarkers or novelty. Equal-plant MAE reflects the declared group policy; diagnostic perturbations and rule complexity omit the upstream image/calibration pipeline. Full-pipeline simplicity and scientifically justified measurement-error stability remain unassessed.

## Verification and custody

`NATIVE_TOMATO_VERIFICATION.json` records exact public-data parity, unchanged partitions and byte-identical replay from the isolated installed package. All 347 sample/group identities and permitted numeric values are checked. Public outputs contain train/dev targets and test inputs only; test target values never enter exported rows or lineage. Original source files, frozen data packages and campaign records remain unchanged. Private drafts are not counted as newly admitted scenarios.
