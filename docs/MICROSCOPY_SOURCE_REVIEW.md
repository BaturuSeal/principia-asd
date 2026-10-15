# P100-070 magnetic-map reconstruction and development-strip audit

This private draft reproduces the historical task without changing its rows, partitions, rules, metrics or failed attempts. It reveals a preparation defect; replay does not constitute scientific admission or a corrected comparison.

## Bound sources and attribution

The registered release projection identifies [Zenodo 14776881](https://zenodo.org/records/14776881), DOI `10.5281/zenodo.14776881`, deposited by Zheng Gong for *Imaging Localized Slip-induced Frictional Heating during Laboratory Earthquakes Using Magnetic Microscopy*. The preserved source metadata declares CC BY 4.0 and publication on 31 January 2025. Acquisition dates are not independently established. MAT creation headers record July 2023 and January 2024; these are file-generation timestamps, not proof of observation dates.

The recipe binds the two original `CSH_FOV5_Bz_uc0.mat` and `CSL_FOV4_Bz_uc0.mat` maps, source metadata and original README. Map SHA-256 values are `38574d68b3536acca8d4cc74f0e1fc33493be859bd32cbdd1448bb0b0ec0b8ff` and `60f0899261d293349c81ab8614bd0499b020e932a50a2f32d1329ff7ecf4e662`. The historical native specification, source manifest and exact compact contract are also bound. Final attribution/notice packaging and scientific admission remain open.

The source README associates CSH/FOV5 with specimen 119DOA and CSL/FOV4 with specimen 129DOA. It names map suffix `uz0`, while registered files use `uc0`. This discrepancy remains explicit; no similarly named file is silently substituted and no physical meaning is inferred from the suffix. Panorama maps omitted by the original selection are not synthesized.

## Numeric decoding and predictor custody

Each MAT file contains six arrays: `Bt`, `Bz`, `corners`, `h`, `newLED` and `step`. Both Bz maps are **1,200 × 1,920**, with no nonfinite pixels. The new decoder supports only bounded little-endian MATLAB-5 real dense numeric matrices. It checks compressed/expanded byte limits, exact variable inventory, flags, dimensions, byte counts, geometry, duplicate variables and trailing data before producing arrays. It rejects complex, object, sparse, unknown and oversized states. MATLAB's integer packing of double-class corner coordinates and LED arrays is handled explicitly. No MATLAB code or object deserialization executes.

Only Bz is used for scientific values. Bt and LED payloads are type/shape checked but not converted into predictors. MCMC estimates, temperature profiles, deconvolution products, inferred maximum-temperature fields and other response channels are neither read nor used. The two full source files remain outside upload roots.

Sampling preserves the legacy zero-based lattice: centers every 20 pixels starting at `(20,20)`, stopping before the last eight rows/columns. Each center uses twelve fixed offsets: horizontal and vertical neighbors at 4 and 8 pixels, plus the four diagonals at 4 pixels. It yields **5,605 centers and 67,260 distinct predictor pixels per map**, with no target/predictor intersection and no overlap between predictor stencils. All source stencils are finite; hypothetical missing stencils are explicitly inventoried without imputation.

Features retain exact historical arithmetic: inner horizontal/vertical averages, outer horizontal/vertical averages, mean diagonal value, minimum and maximum neighbors, and absolute inner-axis differences divided by the twelve-neighbor RMS with a fixed `1e-15` floor. There is no fitted calibration, target-dependent scale or learned transformation. Coordinates, map variable, specimen, region and stencil definition are retained in lineage. Signed fields and source noise are preserved; no smoothing or denoising is added.

The source stores `h = 5e-6` and `step = 1.1699999999999998e-6`, plus corner indices. Their units are not encoded in the MAT arrays. The task's source-native units and unresolved SI conversion remain unchanged; the utility does not assert a physical field scale or pixel-distance calibration. Upstream instrument reduction and reconstruction of Bz from instrument observations are not independently reproduced.

## A fifth preparation defect

The exact historical allocation is **4,501 train / 1,104 dev / 5,605 test rows** across **29 / 7 / 36 spatial blocks**. All CSH pixels stay in development and all CSL pixels stay in test. That specimen boundary passes. The 200-row × 320-column blocks preserve exact old membership; they are not additional independent specimens.

However, the task contract states that development folds are whole 200-row strips. Five CSH strips—`r00`, `r01`, `r03`, `r04`, `r05`—contain both train and dev blocks. Only `r02` remains all train. Thus the compact allocation fails the declared whole-strip separation. The reader records both a passing historical block check and a failing whole-strip check. **The passing block check must not be substituted for scientific contract compliance.**

No correction is made to the frozen edition or its comparison. A new reviewed contract, explicit spatial dependence policy and new frozen cohort are needed. Even corrected strip separation would not create independent experimental replication: only one specimen supplies development and one supplies confirmation. Spatial correlation can persist despite disjoint pixels and nonoverlapping stencils.

## What the results can establish

The task is interpolation of withheld pixels in a stored magnetic map, conditional on neighboring measurements from the same acquisition. It is not earthquake forecasting, temperature inference, mechanistic identification or validation of the source heat-diffusion model. Strong predictive accuracy may reflect spatial regularity and map processing. Its value as an active ASD task requires review; a diagnostic/control role may be more appropriate.

All historical sources and reference outcomes remain retrospective and publicly exposed. Equal-block MAE is the frozen descriptive metric, not an uncertainty estimate over independent earthquakes or specimens. Perturbation sensitivity is diagnostic, and historical rule complexity excludes map reduction and neighbor-feature operations. Novelty, causal meaning, practical impact and external validation remain unassessed.

## Reproduction boundary

`NATIVE_MICROSCOPY_VERIFICATION.json` records exact values and identities for all **11,210 rows**, unchanged partitions, source hashes and byte-identical replay using the isolated installed package. Preparation makes no API calls and performs zero fits. Public tables contain test inputs only; test target values are absent from exported rows and lineage. Source reconstruction remains a curator operation because raw maps themselves contain historically exposed target pixels.
