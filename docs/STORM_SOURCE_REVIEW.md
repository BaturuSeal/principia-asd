# P100-018: tornado report source and dependence review

The native draft exactly reconstructs the historical task. It is **not admitted** to a new scientific edition. Whole recorded episodes stay together, but this is not evidence that tornadoes or outbreaks are independent across partitions. Original campaign results remain unchanged.

## Registered source custody

The canonical scenario is `P100-018`, NOAA Storm Events 2025 details, fatalities and locations, joined through its scenario descriptor, provenance manifest and file hashes. Observation year 2025, file creation snapshot 2026-08-19 and recorded local retrieval 2026-08-23 are distinct dates. The exact details gzip SHA-256 is `d9b46b4c6aae554723cadbb9691f3d5258371c02e530ba815d6fe41e4550149f`.

The four registered source assets are all hashed. Only the details table supplies measurements; fatalities and locations are excluded auxiliary acquisitions. The retained official `Storm-Data-Bulk-csv-Format.pdf` (SHA-256 `3bd18968d34da43e192f8a7fb8e5548c4fa7d24ede016d2d068d849ee1392df6`) supports the event/episode definitions on page 1, local standard time on page 3, reported property-loss and path-length definitions on page 4, and width/continuation definitions on page 5. The authoritative landing reference is [NOAA NCEI](https://www.ncei.noaa.gov/stormevents/ftp.jsp). No source was downloaded again.

The historical local manifest labels the files U.S. Government public data. This review preserves that evidence; it does not establish third-party content exceptions, complete notice obligations or publication authorization. Final rights/notice packaging remains pending.

## Measurements and preprocessing

The gzip expands to 71,101,206 CSV bytes containing 72,360 source records. A bounded reader validates unique event IDs, required fields, exact row shape, source year and timezone, and tracks both CSV record indexes and physical line spans for quoted multiline narratives. It retains 1,591 tornado records before eligibility.

Exactly 295 tornado reports lack a parseable property-loss estimate. They are inventoried as unavailable, never changed to zero. The 1,296 eligible reports include 620 recorded zero-loss values. A recorded zero is not verified absence of all economic loss. The response is `log1p(reported USD)` after explicit K/M/B conversion. Path length is miles × 1.609344; width is yards × 0.0009144; duration is end minus beginning local-standard time in minutes. Latitude and calendar month are retained. No normalization, fitting, imputation, response-based ranking or learned feature extraction occurs.

EF damage scales, casualty/crop-loss columns and narratives never become model inputs. These are post-event path and loss reports; the task cannot establish a pre-event meteorological forecast, insured-loss estimate, mechanism or causal relationship. Source estimates, damage reporting, unobserved exposure and revisions remain limitations.

## Partition and continuation audit

The original confirmation allocation hashes all 553 source episodes before eligibility and reserves 110. Of the 457 episodes with eligible records, 291/72/94 go to train/dev/test, yielding 853/219/224 rows. Exact public cohort IDs, group IDs, numerical values and original partition membership are preserved. All test outputs are omitted from reconstructed tables; evaluator targets are never accessed.

The official continuation fields indicate that a tornado segment can continue into another office/county. The audit matches subsequent office, county FIPS/name and an exact boundary time converted using the stored fixed timezone offset. State abbreviations are retained but not silently equated with full state names. These are **candidate links**, not new adjudicated tornado identities.

There are 253 candidate links; 239 have a unique candidate for their originating event. Forty-three source continuation records have zero or multiple matches. Twenty-six eligible candidates cross partitions: 15 train/dev and 11 train/test. Broad temporal/meteorological dependence can also exist without a recorded continuation. State, track and broader outbreak adjudication are needed before independent-tornado claims or a corrected split policy. The current contract already discloses possible inter-episode dependence, so this is recorded as a concrete scope limitation rather than silently rewriting its grouping contract or adding an unproved identity correction.

## Replay, exposure and release boundary

See `NATIVE_STORM_VERIFICATION.json` for isolated installed-wheel replay and exact parity. The recipe and bounded reader are portable curator tools; raw source responses remain historically exposed. New filenames or partitions cannot turn this into independent evidence. A reviewed new edition would require new immutable scenario identities/contracts and comparisons where changed splits matter.

The UI and static Rule Cards carry a contract- and input-hash-bound scope advisory. The frozen numerical records, all assigned outcomes and existing ranking remain unchanged. Novelty, practical value and external scientific review remain `not_assessed`.
