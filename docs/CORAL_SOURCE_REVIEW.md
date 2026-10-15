# P100-020: NOAA Coral Reef Watch native SSTA and spatial-split review

All 7,419 historical rows reconstruct exactly from the registered native NetCDF. This is a **private reconstruction draft**, not admission into a new edition. No original data, task contract, score, rule or paid attempt changes.

## Source identity and processing

The canonical case is P100-020, the NOAA Coral Reef Watch daily 5 km sea-surface-temperature anomaly product for **16 August 2026**. The registered source is `ct5km_ssta_v3.1-clim19912020-v1_20260816.nc`, 10,707,615 bytes, SHA-256 `a72401223bebfb8d8df5ffadfc46db3ebc17ccb40160f802daaf26c411ef8267`. Its matching PNG is hash-bound provenance only and is never decoded into predictors. Existing local data were used; nothing was redownloaded.

The file identifies product version 3.1, CoralTemp v3.1 source and a derived L4 satellite SST analysis, with the 1991–2020 climatology v1 encoded in its registered filename. This is **already processed, calibrated and climatology-adjusted data**, not raw radiances or independent thermometers. Upstream spatial analysis, calibration uncertainty and climatology construction are inherited and not independently reproduced. A new split cannot remove prior exposure or shared processing.

The local manifest records U.S. Government public data. The file's license permits use without restriction while asking for appropriate NOAA Coral Reef Watch credit, DOI/citation and website notices. This is recorded source evidence, not completed notice/rights approval. The source reference is [NOAA CRW SSTA](https://coralreefwatch.noaa.gov/product/5km/index_5km_ssta_clim19912020.php). Exact citation and final distribution packaging remain open.

## Native decoding and measurement inventory

The anomaly array is int16 with shape 1 × 3,600 × 7,200. Its scale is 0.01 degree Celsius per stored unit, fill value −32,768 and valid stored range −1,500 to 1,500. The uint8 mask has the same shape: 0 valid water, 1 land, 2 missing, 4 ice and fill 251. These values are checked against native attributes, not inferred from the plotted image. Latitude and longitude are float32 centers on a 0.05-degree EPSG:4326 grid. The native reference time is 1,439,726,400 seconds since 1981-01-01; coverage is 2026-08-16T00:00:00Z through 2026-08-17T00:00:00Z.

The bounded reader checks source/version/date, exact shapes/dtypes, grid values, units, axis order, scale/fill/range, mask meanings and reference time before numerical sampling. It denies soft/external links, external storage, virtual datasets and nonapproved HDF5 filters. Only built-in shuffle and deflate are accepted. Optional h5py/HDF5 and decoder binary hashes are bound in the replay environment. No plugin decoder, credential, network call or evaluator vault is needed.

## Expanded preprocessing and eligibility

Sample zero-based rows/columns beginning at 20, at stride 40, retaining centers at absolute latitude at most 60 degrees. Each center uses twelve fixed neighboring cells: ±4 and ±8 pixels on each axis and the four ±4 diagonal cells. The center and all neighbors must be finite valid-water values within ±15 degrees Celsius. The historical eligibility rule uses target quality/range retrospectively; this is not an operational missing-observation forecast.

Of **10,800 candidate centers**, **7,419 are eligible** and **3,381 excluded**. Each excluded stencil fails both the water and native-range conditions; those overlapping reason counts must not be added. Across all 140,400 candidate stencil positions, there are 100,664 valid-water, 37,289 land, 1,771 missing and 676 ice flags. Nothing is imputed or silently resampled.

Inputs `hx/hy/ox/oy` are four opposing-neighbor means; `dg` is the four-diagonal mean; `gx/gy` are absolute opposing-neighbor differences in degrees Celsius; `clat` is cosine latitude. Float32 coordinate arithmetic is preserved for exact historical parity. The target is the center anomaly. Local preprocessing performs **zero fits**. That does not imply zero upstream fitted state: L4 analysis and climatology remain external processing, excluded from historical rule-only complexity.

Lineage retains each center's native row/column and refers to one shared, ordered offset inventory. This identifies every source cell without repeating identical stencil metadata thousands of times. It does not export test response values.

## Split integrity and scientific limits

There are **116 whole 20-degree tiles**, allocated unchanged as **75 train / 18 dev / 23 test**. The **4,804 / 1,277 / 1,338 rows** reproduce all original identities, features and development responses with zero numerical differences. Original confirmation allocation follows the fixed P100-020 tile hash, independently checked by the reader.

No sampled target cell occurs among any predictor cells. No predictor cell is reused across selected stencils. All twelve inputs remain in the center's tile: **zero cross-tile input references**. These checks establish source-coordinate separation and the declared whole-tile partition; they do not establish statistical independence between spatially correlated tiles.

All tiles belong to one already processed daily map. Neighbor distance, shared climatology and L4 spatial analysis make this a retrospective local interpolation diagnostic. It does **not** establish temperature forecasting, coral bleaching prediction, temporal climate trends, causal mechanisms, independent discovery or novelty. Stability remains diagnostic because the measurement-error distribution is not independently established.

`NATIVE_CORAL_VERIFICATION.json` records exact permitted-data parity, source hashes and byte-identical installed-wheel replay. UI and static reports display a contract/hash-bound scope advisory while preserving all canonical metrics and attempts. Final scientific contract, rights/notices, admission and external review remain open.
