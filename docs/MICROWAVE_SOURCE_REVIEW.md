# Parametric microwave scattering: native reconstruction and scope

Reviewed 13 October 2026 (Shanghai). P100-028 remains a retrospective research candidate. Native reconstruction verifies measurement lineage; it does not admit a new scenario or establish inverse-design capability.

## Registered source and selection

Zenodo record **18938314**, DOI `10.5281/zenodo.18938314`, version 1.0 supplies `2025-11.hdf5`. The source record declares CC BY 4.0. Its README links acquisition `2025-11-21_16_40_49` to Figure 4. The record, HDF5 file and README are individually hash-bound by `configs/preparation/P100-028.raw-v1.json`. These existing local assets were reused unchanged; redistribution notices and final admission remain pending.

Only the corresponding group under `Scattering` is decoded. The source's other acquisition, derived `.npz` matrices, inverse-problem solvers, optimized pumping schemes, images and notebooks do not provide predictors. The explanatory notebook was read to verify axis semantics, but none of its code is executed or copied into the reader.

## Measurement and calibration contract

The native USB dataset is complex128 with exact shape **(1, 51, 1, 1, 1, 13, 13)**. Its axes are detuning, frequency-conversion pump control, its phase, parametric-pump control, its phase and two matrix axes. Singleton dimensions and their stored controls are verified before selecting the 51 matrices. Native units are `fsu complex`; the scalar target is magnitude in source full-scale units, not watts or a dimensionless gain inferred from other data.

There are **8,619 complex values**. Each matrix contributes 156 directed off-diagonal pairs. The 663 diagonal values are excluded by structure, not response quality. The two directions remain distinct; the reader never transposes, averages or assumes reciprocity. Physical input/output orientation is not independently certified by these stored axis labels.

The 13 signal frequencies span **4.1994–4.2006 GHz**, exactly 100 kHz apart. The twelve stored conversion pump frequencies are 100 kHz through 1.2 MHz. Stored phase controls, detuning and scheme identity are also checked. Pump amplitude has an initial zero followed by fifty evenly spaced controls from 0.13 to 0.18 fsu.

Each directed pair uses only its measured responses at pump indices **0, 1 and 11** (0, 0.13 and 0.14020408163265308 fsu) as calibration. Complex magnitudes provide `noise`, `lo` and `hi`; `r` is the current pump-control increment divided by the two nonzero calibration controls' increment. These operations have no learned parameters or optimization. The source `USB std` array is not used to claim independently verified uncertainty.

Indices 12–50 produce **6,084 task rows**. The intermediate noncalibration indices 2–10 remain in the exclusion inventory. All selected measurements must be finite; changed or missing measurements fail reconstruction rather than reducing coverage. Per-row lineage names the dataset, all seven zero-based coordinates, calibration indices, native frequency pair and direction convention. Test responses never enter exported inputs; the evaluator vault is not read.

## Partitions and limits

The unchanged compact allocation holds out the ten highest pump matrices, indices 41–50 (**0.17081632653061224–0.18 fsu**). The remaining 29 matrices contain 24 train and five dev groups, with every directed pair kept together. Counts remain **3,744 train / 780 dev / 1,560 test inputs**. Development matrices are hash-selected, not a newly claimed chronological split; the earlier five-fold labels do not control this compact allocation.

All matrices share one acquisition and low-pump calibration. Whole-matrix separation does not create independent instruments or replicate acquisitions. This is magnitude extrapolation conditional on measured calibration, not recovery of phase, proof of a mechanism or inverse pump design. The upstream USB measurement/reduction process and uncertainty require separate review. Historical rule complexity excludes the magnitude and calibration preprocessing; the report states that limitation without changing frozen numerical scores.

## Decoder and reproduction

Install `principia-asd[curation]` in a separate curator environment. Ordinary scenario exploration does not require this optional dependency. Missing HDF5 support fails explicitly. The preparation receipt binds h5py/HDF5 versions and the h5py core extension hash in addition to Python source and numerical-library bindings. A changed decoder fails replay before producing output.

The reader bounds file size and exact dataset shapes/types before loading, and rejects indirect/external links, external raw storage, virtual datasets and filters. These checks follow the official [h5py dataset interfaces](https://docs.h5py.org/en/stable/high/dataset.html) and [group/link interfaces](https://docs.h5py.org/en/stable/high/group.html). It reads only the registered local file and never executes upstream code.

`docs/NATIVE_MICROWAVE_VERIFICATION.json` records exact public parity, original-file preservation and isolated installed-wheel replay. The private draft is separate from the frozen edition. Source notices, scientific contract admission, calibrated perturbations and a future versioned comparison remain open gates.
