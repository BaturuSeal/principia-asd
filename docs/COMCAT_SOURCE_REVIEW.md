# P100-017: USGS catalog-origin diagnostics

This review reconstructs the frozen retrospective task without changing its rows, partitions, attempts or metrics. The proposed role for a new edition is **diagnostic, pending scientific review**. Catalog-reported uncertainty is not independently measured prediction error, and a fitted relation between products of one location solver does not establish a newly discovered geophysical mechanism.

## Source identity and snapshot

The four registered local assets are July 2026 ComCat QuakeML, GeoJSON, the count response and service version. Their hashes are bound in `configs/preparation/P100-017.raw-v1.json`; none was downloaded again. Both representations contain exactly **2,607 uniquely identified events**, matching the count record and service **2.7.0**. GeoJSON's generation timestamp is **23 August 2026, 13:15:45 UTC**; local provenance records retrieval completion at 14:14:09 UTC that day. These are acquisition/version times, not earthquake occurrence times.

All QuakeML events contain exactly one origin and explicitly prefer that origin. Every event query ID matches its source attributes and GeoJSON identity. Finite shared location/quality values agree across formats. This snapshot therefore resolves the concern that the historical reader selected a nonpreferred first origin. A future file containing multiple or conflicting origins fails explicitly and requires a new reviewed recipe.

The recorded query selects earthquakes from 1 July to 1 August 2026 with minimum magnitude 2.5. Official [FDSN API documentation](https://earthquake.usgs.gov/fdsnws/event/1/) defines the upper timestamp as inclusive; the old local prose called it exclusive. Actual source events run from 1 July 00:14:00.949 to 31 July 23:46:39.943 UTC, so no boundary event or historical row changes. The API also documents preferred-catalog selection. Future live acquisition must use frozen versions and explicit boundary handling.

## Quantity classification and exclusions

Inputs are reported depth (metres converted to kilometres), phase residual standard error, used phase/station counts, azimuthal gap and minimum angular station distance multiplied by the historical fixed factor 111.195 km/degree. The response is `origin.depth.uncertainty`, converted from metres to kilometres. Negative reported depths are preserved. No imputation, learned transformation or new fitting occurs.

Depth and uncertainty are source-fitted location quantities; residual error is a fit diagnostic, and station geometry/counts are derived supporting metadata. The input is not an archive of raw waveforms or phase arrival measurements. USGS distinguishes [origin and phase-data products](https://earthquake.usgs.gov/data/products/); this task uses the former's catalog summaries. The [ComCat documentation](https://earthquake.usgs.gov/data/comcat/) describes contributions from multiple seismic networks. Shared network/model errors remain possible across our spatial clusters.

The historical eligibility rule retains **2,545 events** and excludes **62**: 41 have zero reported depth uncertainty; 21 lack QuakeML minimum station distance. All excluded identities and reasons remain in the reconstruction inventory. The missing-distance entries include **20 for which GeoJSON supplies zero**, plus one for which both representations lack the field. The reader records these differences and does not replace missing XML values with apparent zeros. These exclusions were already in the frozen task; they are not post-hoc pruning based on new model performance.

None of the 2,607 origins supplies `depth.confidenceLevel` or `depthType`. Consequently this preview does not assign an unrecorded 95% or one-sigma interpretation, or claim that zero uncertainty establishes a known fixed true depth. The target is the supplied catalog quantity. Coverage means the frozen eligible cohort, not all events or all real earthquakes above the nominal threshold.

## Components and partitions

The complete catalog is clustered **before eligibility**. Edges connect events at most 100 km apart by Euclidean chord on a sphere of radius 6,371 km, and at most seven days apart. The radius is not a surface-arc calculation. Connected components are transitive; an ineligible event may bridge two eligible ones and must not be dropped before graph construction.

There are **49,512 candidate spatial pairs, 30,506 accepted space/time edges and 651 components**. Five components have no eligible rows, leaving 646 evaluated groups. The largest component contains 607 events. The maximum component time span is about 30.98 days: the seven-day limit applies to edges, not entire components. This is recorded rather than misrepresented as independent seven-day windows.

Original confirmation uses the metadata hash allocation over all 651 components. The existing compact development allocation remains unchanged: **413 train / 103 dev / 130 test groups**, containing **1,194 / 1,080 / 271 rows**. Group separation passes. Networks and velocity models can nevertheless recur across partitions, and the random component split is neither chronological transfer nor a held-network study.

## Reproducibility and remaining gates

The bounded native reader verifies XML namespaces, unique event/origin identities, preferred-origin binding, UTC timestamps, coordinate/count domains, source counts and cross-format values. It rejects entity declarations, duplicate fields, unknown JSON constants, unsupported schemas and excessive graph work. It preserves exact unit conversions, event-index/origin lineage, all graph memberships and all eligibility exclusions. Test targets are omitted from the prepared public tables. Protected evaluator outputs are never opened by native preparation.

The source-field and graph definitions are independently implemented from the original local native preparation specification, whose hash is retained. Exact reader/utility, NumPy and SciPy bindings and a private source snapshot support replay. `NATIVE_COMCAT_VERIFICATION.json` records isolated installed-wheel replay and historical package preservation. No old runtime, reference formula or source-fitted rule is copied into the engine.

Source rights/notices, contributor attribution, scientific interpretation and justified perturbation standards remain pending. The inherited public-domain label is not treated as a completed audit of every contributor's obligations. Without independent error observations or a stronger reviewed question, this is a useful catalog-diagnostic/control task rather than an active claim of scientific discovery. It does not increase the admitted-scenario count or alter the primary leaderboard.

Verified on **12 October 2026 at 07:14 UTC**: all 2,545 eligible rows and generated artifacts replay exactly from the separately installed wheel, with zero numerical differences and every historical scenario file unchanged. The private draft is **1,290,173 bytes expanded / 1,115,005 stored**. The full suite passes **324 tests** (27 new ComCat checks), Ruff, JavaScript syntax, clean installation, 12 CLI help paths, numerical execution and HTTP security checks. Read-only browser verification confirms the existing task context, 16-rule/13-attempt leaderboard and a Principia Engine Rule Card. No new discovery was dispatched, and the source review does not use final-test performance.
