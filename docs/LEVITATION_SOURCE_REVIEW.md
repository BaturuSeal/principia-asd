# P100-068: raw acoustic-levitation traces

This curator review reconstructs the historical acquisition-based task. It does not admit a new scenario or change any frozen measurements, rules, metrics or attempts. The data are retrospective and already publicly exposed.

## Source and custody

The registered source is Mehdi Akbarzade, *Sparse identification of nonlinear dynamics applied to the levitation of acoustically large objects*, [Zenodo record 16033764](https://doi.org/10.5281/zenodo.16033764), dated 17 July 2025. The locally preserved record identifies CC BY 4.0. Final attribution, rights scope and scientific-contract approval remain pending; this review is not legal clearance.

`configs/preparation/P100-068.raw-v1.json` binds the four original local files: `Data.rar`, the two Matlab descriptions and `source_record.json`. No acquisition was downloaded again. The archive contains 31 raw `data…n.mat` files, 31 matching `data…de.mat` files and a ReadME. The ReadME describes varied external excitation, raw noisy measurements and GHKSS-denoised signals; its text says `dn` although actual file names use `de`. Pairing follows the observed inventory and matching clocks, not a guessed suffix.

The original Matlab descriptions are documentation only. Their PSD, integration, differentiation, illustrative velocity calibration and identified coefficients are excluded. The historical native preparation definition is independently implemented with its source hash retained for attribution. No Matlab code, upstream fitting routine, legacy runtime, reference equation or evaluator vault is executed or read.

## Measurements and timing

Each raw file contains 999 `t`/`noisy_s` observations. Thirty traces use 0.5 ms sampling, from 0.0005 to 0.4995 seconds. `data1172n` uses 1 ms sampling, from 0.001 to 0.999 seconds. There are **30,969 raw voltage observations** and 31 distinct full-signal fingerprints. Every denoised counterpart has the exact same clock as its raw trace; its values are read for numeric-schema validation only and never enter a feature, calibration or target.

For each trace, the first 20 raw values define an explicit mean offset. The final calibration timestamp is 10 ms or 20 ms, depending on sampling. Prediction begins at native index `round(0.05/dt)`: the actual first issue is 50.5 ms or 51 ms because the stored clock begins at `dt`, not zero. Subsequent issues are spaced by 5 ms. The target is raw voltage 5 ms later; inputs are offset-centred voltage at issue time and 5, 10 and 15 ms earlier, plus the offset and stored issue time. Each actual horizon and delay is checked against timestamps with a 1e-12 second tolerance. No filtering, interpolation, fitting, normalization or response-dependent selection is added.

The resulting historical cohort has **2,859 rows: 1,880 train, 445 dev and 534 test inputs**. The 1 ms recording contributes 189 rows; each of the other 30 contributes 89. Every declared eligible window is retained. There are no nonfinite-window exclusions in these source files. Full native zero-based index lineage is retained without exporting held-out response values.

## Partition and claim boundaries

The existing whole-trace allocation remains **20 train / 5 dev / 6 test**. Raw/denoised pairs are linked and never allocated separately. Reconstruction checks exact sample IDs, group IDs, development values and permitted test inputs. It never opens protected test targets.

This is **online, short-horizon voltage prediction within one levitator/object setup**. Earlier measurements of a held trace deliberately become permitted later inputs; test outputs are therefore not permanently unobservable measurements. The benchmark is not a free-running rollout, an independent-device test or identification of a mechanical law. File identities and distinct signals do not resolve shared apparatus dependence or establish which excitation regimes are new. Sensor calibration, acquisition latency and scientifically justified perturbation distributions remain review requirements. Predictive parity cannot resolve these limitations.

## Reader and reproducibility

The reader checks the source archive hash before bounded decoding. It permits only expected regular MATLAB files, the ReadME and their directory; links, duplicate or unknown entries, excessive expansion and decoder warnings fail. Archive output is streamed with byte and time caps and never extracted to a source folder. The recipe pins the system decoder's executable hash and version. An unavailable or different bsdtar/libarchive decoder raises an explicit error; replay never installs or silently substitutes one.

MATLAB decoding admits only two plain uncompressed little-endian numeric vectors per member, with bounded dimensions, matching lengths, real finite values and the registered clock. Compressed streams, additional hidden state, malformed arrays and irregular or shifted clocks are rejected. NumPy, SciPy and exact reader hashes are bound in the preparation environment. Old drafts retain their previous wheel/runtime bindings.

The separate installed-wheel replay receipt is `NATIVE_LEVITATION_VERIFICATION.json`. The private draft and its reader snapshot stay outside the three upload roots. Passing reconstruction does not clear source-rights, contract or independent-evidence gates.

Verified on 2026-10-12T06:03:23.137791+00:00. The clean installed wheel reproduced every generated artifact byte-for-byte; all historical scenario files remained unchanged. Development measurements and permitted test inputs have zero numerical differences. The private draft is **1,305,003 bytes expanded / 907,628 bytes stored**. The complete suite passes **297 tests**, including 28 new clock, calibration, online-prefix, paired-custody, numeric-schema, archive-bound and decoder-failure fixtures. Native reconstruction made no API calls, performed no fitting and did not access the evaluator vault.
