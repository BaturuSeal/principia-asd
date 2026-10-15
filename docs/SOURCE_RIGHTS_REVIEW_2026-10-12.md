# Source-rights evidence: first three-case review

This is an evidence audit, not blanket redistribution or scientific approval. It supplements the frozen edition without modifying scenario bytes, task contracts or admission decisions. [The machine-readable receipt](source-reviews/2026-10-12-initial-three.json) verifies every registered original source hash for P100-017, P100-043 and P100-054. The other 37 active packages still need this deeper review; all 100 historical audit outcomes remain retained.

## P100-043: Gemstones training trajectories

The local copyright notice exactly matches the scenario's recorded SHA-256. Its Git blob identity also matches the preserved, nontruncated source tree, which lists the two original training-log files. The [pinned upstream notice](https://raw.githubusercontent.com/mcleish7/gemstone-scaling-laws/5f420478f6057b0cbb4d13405fb10ca64675bccb/LICENSE) states MIT terms and names the authors. Source revision: `5f420478f6057b0cbb4d13405fb10ca64675bccb`.

The release package needs the complete original copyright/license notice, attribution, and an explicit description of measurement extraction and partition changes. Before closing the gate, review the scope of the repository license for the redistributed numerical records, check for separate third-party conditions, and verify the public package carries the notice. This review does not infer permission for unrelated upstream training corpora or model weights. Scientific admission remains separate.

## P100-054: microfracture measurements

The preserved [Zenodo record](https://zenodo.org/records/15581944) identifies DOI `10.5281/zenodo.15581944`, lists seven creators and declares `cc-by-4.0`. Its original archive is 36,678,522 bytes, with recorded MD5 `adcb5e7bd19aecc2ea70b5aaf2c23901`; the local registered archive and metadata SHA-256 checks pass. The compact package is a derived measurement subset, not the complete raw trace archive.

Under the [CC BY 4.0 terms](https://creativecommons.org/licenses/by/4.0/), the release should provide author credit, the original title and DOI, the license link and an explicit indication of changes. The attribution should name Eloho Okotete, Alban Muslija, Judith Hohmann, Manfred Kohl, Steffen Brinckmann, Subin Lee and Christoph Kirchlechner. Do not conflate repository-metadata CC0 terms with the dataset's CC BY terms. The current landing page was checked; its API/license field was not available through the browsing tool, so the license evidence here is the hash-verified preserved repository record.

The final review must check archive-internal notices and verify that the preprocessing description accurately identifies measured geometry, author-derived quantities and the retrospective observation window. Attribution readiness does not establish a pre-test causal or predictive interpretation.

## P100-017: ComCat earthquake diagnostics

The inherited label says U.S. Government public domain. The original local snapshot contains 2,607 events from 11 preferred network codes: `us`, `hv`, `ci`, `pr`, `tx`, `ak`, `nc`, `uw`, `uu`, `nn`, `av`. Preferred-network identity is not a complete product-rights determination. The compact eligible cohort is smaller than the raw snapshot, so raw network totals must not be mistaken for admitted-row totals.

[USGS's copyright policy](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits) distinguishes USGS-authored material from third-party content. [ComCat's documentation](https://earthquake.usgs.gov/data/catalog/contribute/) confirms that other networks contribute products. Therefore the blanket inherited label alone is insufficient evidence to close this release gate. Review terms and attribution for the contributing data actually retained, and preserve their original attribution. This is a provenance gap to resolve, not a finding that the data are prohibited.

## Next release action

Prepare per-scenario attribution and notice files for the next unfrozen public edition, validate them against the source hashes, then complete source-rights and scientific-contract decisions separately. Do not retroactively relabel the frozen numerical campaign as publicly approved. No raw data were redownloaded and no source package was modified during this review.
