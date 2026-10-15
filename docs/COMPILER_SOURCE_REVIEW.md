# Circuit compilation: native timing reconstruction and diagnostic scope

Reviewed 13 October 2026 (Shanghai). P100-031 remains a retrospective candidate. This source review recommends retaining it as a **diagnostic/control task** pending scientific admission, rather than presenting its timings as discovery about quantum devices.

## Source and exact joins

The registered source is Zenodo **14977295**, DOI `10.5281/zenodo.14977295`. Its metadata describes published Benchpress 1.0 results and declares CC BY 4.0. The metadata and `published_results.zip` are hash-bound; no files were downloaded again. Attribution/notice packaging and final scientific admission remain open.

The archive has 66 entries and 14,715,094 expanded bytes. Only four `published_results/transpilation/*_device.json` members are read: Qiskit, TKET, BQSKit and Staq. Circuit construction/manipulation, cloud-service and abstract-connectivity results are excluded. No source compiler, QASM program, notebook or old runtime executes.

The four reports contain 447 benchmark records, including 185 filename-bearing successful records and 262 other benchmark records. Exact filename joins link 50 Qiskit pilots to 47 TKET, 38 BQSKit and 50 Staq outcomes. Both filename and input-qubit count are checked. Duplicate keys, circuit IDs, ambiguous SDK names, status inconsistencies and altered cohorts fail reconstruction.

The resulting **135 successful compiler–circuit pairs** retain every historical task row. The 15 other candidate pairs remain in a source exclusion inventory: three TKET `xfailed` circuits and twelve BQSKit `failed` circuits. They are neither imputed timings nor newly inserted benchmark attempts. The historical task is conditioned on successful compiler execution and cannot quantify failure prediction or overall compiler reliability. Source-suite status counts are reported separately from this selected named-circuit panel.

## What is measured and what must already be known

The target is the author's recorded `stats.mean` compilation time. The source identifies `perf_counter` timing, one iteration per round and varying round counts; minimum, maximum, mean and total/round consistency are checked. Aggregates are preserved rather than inventing raw repeat durations or confidence intervals. BQSKit includes single-round measurements.

Each row's predictors come only from its matched Qiskit pilot: recorded mean runtime, input qubits, output two-qubit gate count/depth and QASM loading time. SDK indicators identify the candidate compiler. Candidate SDK circuit outputs, loading time and timing statistics never enter predictors. Per-row lineage names the JSON member, benchmark-array index and exact input/target fields. Test responses are not exported and the evaluator vault is not read.

The 50 unique Qiskit pilots represent **409.03566056024283 seconds of recorded timing rounds**, plus **0.7251386841526255 seconds of separately recorded QASM loading**. Those aggregates are not a certified end-to-end cost and should not be double-counted as one pilot per candidate compiler. This task requires completing the pilot before prediction; its cost is not free. The native reader itself neither recompiles circuits nor performs model fitting.

## Families, environments and admission limits

The historical family function removes all optional-delimiter numeric tokens anywhere in a filename stem, then lowercases it. For example, `gf2^7_mult` and `gf2^32_mult` map to `gf^_mult`. It is broader than the contract's shorthand about size suffixes. All circuits assigned to the same family and their compiler observations remain linked. The original allocations remain **20 train / four dev / five test families**, yielding **78 / 20 / 37 rows**. Existing exposure exclusions and group hashing are preserved; no final loss influenced selection.

These filename groups are not a verified semantic circuit taxonomy. Original QASM payloads are not among the four selected reports, so circuit equivalence, cross-family relatedness and original circuit correctness remain unverified.

All reports name the AMD Ryzen 9 7900 12-Core Processor, but acquisitions span August 4–16, 2024 and use different Benchpress commits and SDK versions. The recorded software includes Qiskit 1.2.0, TKET 1.31.0, BQSKit 1.1.2 and Staq 3.5, with differing ancillary Qiskit versions. CPU-brand equality does not establish equal CPU load, frequency, thread policy or full environment matching. Exact dates, revisions and version dictionaries are retained in the reconstruction receipt. These are historical versions, not a claim about current compiler performance.

The scope is recorded software runtime conditioned on a completed pilot and successful target execution. Pre-compilation timing, unseen hardware, compiler failure, quantum-device quality and scientific novelty remain unassessed. Unit/domain legality of discovered rules and justified perturbations require separate review. The display advisory changes no historical score, attempt or denominator.

## Reproduction

Use `configs/preparation/P100-031.raw-v1.json` with a new private output directory. `docs/NATIVE_COMPILER_VERIFICATION.json` verifies original-file preservation, exact public-table parity and byte-identical isolated installed-wheel replay. The draft remains outside the frozen edition; no new scenario is admitted by this engineering check. Source rights/notices and a reviewed scientific contract precede any future edition or comparison.
