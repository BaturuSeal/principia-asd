# P100-054: geometry, repeat specimens and native fracture traces

The new curator recipe rebuilds the existing geometry-conditioned task from the registered original ZIP and source metadata. It additionally decodes all raw PI 89 load–displacement traces. This is a source and preparation review, with no model fitting, API calls, evaluator-vault access or selection against test scores. The frozen scenario and previous comparison remain unchanged.

## Sources and measured fields

The original `Data for publication.zip` is bound by its registered SHA-256 and contains the author's summary workbook, README and 107 experimental text files. The source README identifies the PI 89 indenter, low-load transducer setup and the associated Materials Science and Engineering: A article. Existing source metadata records CC BY 4.0; final notice packaging and redistribution review remain pending.

The workbook reader selects only stored specimen identity (A), geometry (B, C, D, E and I) and reported second-bridge failure load Pb2 (G). It validates the native micrometre/millinewton unit headers. Formula cells in these selected fields are rejected, including cached formula values. Source toughness, fitted corrections and all other response-derived columns are excluded. Crack-arrest sheet names are not predictive features or exported lineage labels.

Geometry may have been measured by SEM after testing. The task therefore estimates reported load conditional on reported geometry; it does not demonstrate pre-test experimental control or causal identification.

## Native measurement decoding

All **107 traces, containing 2,458,963 measurement rows**, decode with the declared units: depth in nm, load in µN, time in seconds, and the two instrument voltage channels. The micro sign uses the source's Windows-1252 encoding. Declared point counts match, all five channels are finite and every acquisition clock increases strictly.

Each file contains three blank separator lines. The reader retains their exact positions and maps array rows back to contiguous source-line segments, rather than shifting the source coordinates after blank lines. Negative baseline measurements and abrupt changes are preserved. No smoothing, fitted extraction, outlier deletion or inferred physical event is performed. Both outer ZIP and inner XLSX readers enforce member, expansion, path and relationship checks.

Summary sample IDs join exactly to trace file stems. There are **107 observations and 103 canonical specimen groups**. The repeated labels `2_D18/D18`, `2_D19/D19`, `2_D21/D21` and `E39/E39-2` remain grouped. The inherited conservative normalization also maps `2_D22` to its canonical identity even though there is no paired original trace in this archive.

Full traces contain response information and remain curator-only. They are neither bundled into the compact prediction tables nor made available to discovery workers for the current geometry-to-Pb2 task. The native decoder is available for future, explicitly contracted trace-analysis tasks; it does not automatically admit such a task.

## Split and reconstruction evidence

Complete canonical specimens remain within their historical split: **65 train / 16 dev / 22 test groups**, corresponding to **67 / 17 / 23 task rows**. All sample IDs, groups, inputs and permitted development responses match the historical public tables with **zero numerical differences**. Test response columns are absent from the generated public tables. Repeat grouping does not establish independence across wafers or fabrication batches: this source represents one wafer/manufacturing campaign.

Every generated artifact replays byte-identically from the clean installed wheel. The [verification receipt](NATIVE_FRACTURE_VERIFICATION.json) binds the original assets, reader modules, trace inventory, exact cohorts and replay. Private candidates and exact small source snapshots are kept in `reconstruction-candidates/native-fracture-v1` outside the upload roots. Earlier candidates, source snapshots and wheels remain preserved.

Synthetic tests change undisclosed Pb2 values, raw force amplitudes and author-fitted columns. Public prediction inputs remain unchanged. Tests also reject mismatched specimen/trace identities, changed units, formula-derived selected measurements, invalid geometry, bad point counts, nonfinite channels, ambiguous worksheets and archive path/size violations.

## Scope still requiring review

The target is **stored author-reported Pb2**. A maximum force is not automatically a second-bridge failure event. Independent recovery of that event from these traces remains unvalidated; the reader does not claim it. Author interpretation, specimen preparation, SEM timing, source notices and task-specific perturbation standards require scientific review before admission.

This adds a fifth portable draft recipe. It does not add an active scenario or change the 520-attempt primary ranking. The other 35 compact scenarios still require native preparation and source-specific review. Scientific novelty, independent discovery, practical value and external validation remain unassessed.
