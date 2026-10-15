# Operando LFP XAS: native reconstruction and evidence scope

Reviewed 13 October 2026 (Shanghai). P100-025 remains a retrospective research candidate. This reconstruction verifies the historical measurement pipeline; it does not admit a new independent-discovery scenario.

## Registered sources

The registry resolves this case to Zenodo record **14922524**, DOI `10.5281/zenodo.14922524`, associated with the source paper DOI `10.1039/D5JA00155B`. Both original assets, the record JSON and `data.zip`, are SHA-256 bound by `configs/preparation/P100-025.raw-v1.json`. The local record documents CC BY 4.0. Attribution/notice packaging and final redistribution approval remain pending; no source file was downloaded again or modified.

The archive contains 35 entries (34,567,993 expanded bytes). Only four members are decoded: the unbinned LFP XANES matrix, the FePO4/LiFePO4 measured reference spectra, the LFP spectrum-assignment workbook and the LFP galvanostatic log. Other materials, binned spectra, EXAFS, XRD fitted intensities and CIF states are excluded. The large source archive is curator input and is not bundled in the compact draft.

## Measurements, calibration and missingness

The unbinned matrix has **194 acquisition spectra**, **2,005 energy rows** and **388,970 measurement cells**. Of these cells, **365,514 are finite and 23,456 are missing**. Missing positions remain traceable per spectrum; no imputation or silent row filtering occurs. The energy axis runs from 6,404.221 to 8,408.221 eV in 1 eV steps.

Each task spectrum uses its own 7,000–7,050 eV pre-edge and 7,250–7,300 eV post-edge bands. The first band has 50 source positions, including one missing measurement at 7,049.221 eV in every spectrum; the finite mean therefore uses 49 observations. The post-edge mean uses 50. `pre` is the finite pre-edge mean and `jump` is the post-edge mean minus `pre`. These are declared same-spectrum calibrations, including for held-out spectra.

The reference file has 1,873 energy rows, with gaps of up to 4 eV and no missing reference responses. Each measured reference is normalized using its own pre/post bands. First and second finite differences of the normalized LiFePO4 response use the native nonuniform energy grid. Linear interpolation then supplies reference values and derivatives at the task energies. Every selected target records the interpolation bracket and derivative-support source rows, in addition to normalization bands. No fitted phase fractions, reference equation or hidden encoder enters the inputs.

The task retains 26 fixed energy positions per acquisition, from 7,070.221 through 7,195.221 eV at 5 eV spacing: **5,044 rows**. All selected target cells are finite in the bound source. A missing selected target or invalid calibration fails reconstruction instead of shrinking this denominator. The evaluator vault is not read; test outputs are not exported.

## Acquisition time and grouping

The metadata states 300-second unbinned acquisitions. The stored assignment workbook maps acquisitions 001–107 to charge, 108–131 to rest, 132–170 to discharge, and 171–194 to final rest. Its durations and endpoints are checked against **58,068 electrochemistry rows**, with unit-checked total time and actual segment modes. The discharge log starts at 39,182 seconds and ends at 50,866 seconds, with elapsed segment time 11,684 seconds.

The historical `f` feature uses nominal acquisition midpoints and retrospectively known segment durations. Its discharge origin is the preceding segment's last timestamp, 39,181 seconds. This convention is preserved, including the one-second distinction from the first discharge observation. No hardware synchronization timestamp or independently measured state of charge is inferred. Voltage, current and capacity values are never prediction inputs.

All acquisitions in a triplet stay together: **42 train / 10 dev / 13 test groups**, yielding **3,276 / 754 / 1,014 rows**. The final group has two spectra. Boundary triplets can span cycle phases. Source binned representations are excluded rather than counted as independent evidence. The compact allocation interleaves groups within this single cycle; the legacy five-fold wording does not describe a new chronological split.

## Scientific limits and reproduction

This task assesses calibrated spectral-shape reconstruction within one cycle. Shared measured references, adjacent acquisitions and a common cell limit independence. It does not establish transfer to a new cell, real-time state-of-charge forecasting or a discovered mechanism. The source's mu(E) exports already embody spectroscopy reduction; the package does not reproduce detector-count processing or its uncertainty.

Historical rule-complexity scores describe the submitted rule relative to prepared inputs. They exclude normalization, reference finite differences and interpolation. The exact operations are now auditable, while full-pipeline complexity remains unassessed. The display-only advisory leaves all scores, submitted rules, failures and denominators unchanged.

Use the recipe with a new private output directory and the registered sources. `docs/NATIVE_XAS_VERIFICATION.json` records original-file preservation, exact public parity and byte-identical replay through the independently installed wheel. The private draft and reader snapshot remain under `reconstruction-candidates/native-xas-v1`; the frozen scenario edition is unchanged. Rights, uncertainty, perturbation standards, contract admission and a future versioned comparison remain separate gates.
