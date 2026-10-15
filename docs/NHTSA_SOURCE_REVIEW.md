# P100-019: complaint record-boundary and monthly-count review

Native reconstruction reproduces all **5,642 historical rows exactly**, but independently reading the publisher's literal tab-delimited records identifies a **preparation defect**. Historical results must remain diagnostic. No frozen source, task, target vault, paid attempt or numerical outcome is replaced by this audit.

## Confirmed record-boundary defect

The registered `COMPLAINTS_RECEIVED_2025-2026.zip` is 37,400,118 bytes, SHA-256 `e7a1f8f6ae2122a8a370f1e7231813b5f119d480e91a67da194656e856eced15`. Its single text member expands to 166,583,265 bytes. The local official `CMPL.txt` layout, revised 30 April 2026, specifies tab-delimited records and 51 fields. Every one of the **185,256 physical lines** contains all 51 fields.

The historical preparation used pandas' default quote interpretation. Quotes within the free-text complaint narrative can therefore keep a field open across several complete source records. Reproducing that interpretation yields only **185,080 logical records**. There are **29 merged spans**, absorbing **176 physical records**; the largest span contains 38 physical lines. The selected fields of each merged record match its first physical line, so later records disappear without producing a column-count error. Checking only the decoded row width would miss the defect.

After the prescribed `(ODINO, make|model)` deduplication, the historical parser retains **123,700 vehicle complaints**, while the literal-record reader retains **123,814**: **114 missing unique complaints**. The affected counts span 101 vehicle–month cells over the full source, including **81 cells in the fixed cohort and scored July 2025–July 2026 period**. The original 434-vehicle cohort happens to remain unchanged. Neither a correct split nor exact replay repairs this loss of source observations.

The new reader preserves the historical mode solely to reproduce and bind the existing results. A second, independent literal-TSV pass checks every source record and reports the failed equivalence gate. Its scientific status is a diagnostic draft, not a valid new admission. A separately versioned corrected package/evaluator and frozen comparison are required. This audit does not silently recalculate published scores against changed counts.

## Source custody and excluded data

Only the registered complaints archive and official complaint layout are needed. The old source manifest also names investigations and other archives; those do not enter this task, and some are absent from the publication projection. No similarly numbered folder, missing optional archive or replacement download is used.

Parsing retains only source record coordinates, complaint IDs, make/model, received/added dates and product type inside the curator. **VINs, operator names, contact fields and narratives are never retained or exported.** Personal text is neither a model input nor an audit example. Record-boundary findings expose line ranges, not narrative contents. The installed reader bounds archive expansion, member count/name, compression, physical line length and record count; it rejects traversal, linked/encrypted members, unexpected columns, ambiguous vehicle identities and unknown product codes.

The source layout explicitly distinguishes `LDATE` (received by NHTSA) from `DATEA` (added to the file) and warns that product labels and records can change between outputs. In this frozen selection all retained complaint records have matching added/received dates. That establishes zero recorded lag, **not** verified as-issued publication or completeness. The snapshot was retrieved on 23 August 2026. Existing local provenance records U.S. Government public data; final notices, distribution review and the exact source-version citation remain pending. The recorded landing reference is [NHTSA datasets](https://www.nhtsa.gov/nhtsa-datasets-and-apis).

## Expanded count construction

Filter product type V, valid received dates and nonempty make/model. Strip make/model whitespace, join with `|`, and deduplicate `(ODINO, vehicle)` using the first native record. Repeated components and different model years are not separate count units. The historical source removes 58,869 component duplicates, with no conflicting received dates. ODINO can be shared across models; this is not a unique physical fleet inventory.

Select vehicles having at least six received complaints before July 2025. The actual source begins on 1 January 2025, so this is the declared January–June cohort. Do not enroll vehicles using later responses. For each of 434 fixed vehicles, build January 2025–July 2026 monthly counts, retaining zero months. Inputs are the preceding month's count, preceding three- and six-month means, and target calendar month. No incident date, injuries, fatalities, recall, investigation or manufacturer communication enters a predictor. Local preprocessing performs zero fits; counting and selection are explicit operations.

Lineage binds the archive/member, make/model query, target month, preceding six months and the exact deduplication algorithm. Shared hashes bind the contributing input source coordinates. Source-record lists or counts that would expose future test targets are not exported. Earlier observed test-month counts legitimately enter later inputs under the existing online-history contract; final July counts never affect predictors.

## Partitions, parity and interpretation

The original complete-month allocation is unchanged: **July 2025–February 2026 train; March–April 2026 dev; May–July 2026 test**. This gives **3,472 / 868 / 1,302 rows**, or 8/2/3 whole months. All historical sample IDs, groups, permitted values and development responses match exactly. Evaluator-only targets were not accessed.

The same vehicles repeat across partitions and six-month lag windows overlap. These are three held months in one retrospective reporting snapshot, not independent fleets, defects or incidents. The target is received complaint volume; without exposure denominators and reporting-process validation it does not establish defect risk, incident rates, safety impact or causal discovery. A recorded received-date ordering also does not prove operational data availability.

See `NATIVE_NHTSA_VERIFICATION.json` for historical parity, the failed literal-record equivalence check and installed-wheel replay; `NHTSA_UI_VERIFICATION.json` and `NHTSA_RENDER_VERIFICATION.json` cover the visible defect notice with unchanged canonical outcomes. Source clarification, corrected scientific contracts, rights and new edition admission remain open.
