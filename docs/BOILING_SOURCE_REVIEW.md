# P100-027 — KTH boiling measurements and fixed water properties

This is a private native reconstruction draft, not a new admitted scenario, independent experiment or replacement for the frozen comparison.

## Source and measurement scope

The registry identifies [Zenodo record 14627088](https://zenodo.org/records/14627088), DOI `10.5281/zenodo.14627088`, containing the KTH/HWAT boiling-water experimental databank. The stored metadata credits Jean-Marie Le Corre, Haipeng Li, Dmitry Grishchenko, Aleksander Kipiela, Max Persson, Pavel Kudinov and Henryk Anglart, and declares CC BY 4.0. Fourteen registered local assets (record, README and twelve XML runs) total 4,504,381 bytes. All original hashes match. Final notices, rights and scientific admission remain pending.

Each run supplies twelve radial measurements. The response is the stored local `VOIDFRACTION`, not a reconstruction of raw probe signals. Predictors are absolute pressure (Pa), mass flux (kg m^-2 s^-1), supplied outlet quality (kg vapor per kg mixture), normalized sample coordinate and two pressure-derived density properties. Native radial units and the provenance of outlet quality (measurement versus energy-balance derivation) remain unresolved. The coordinate is exactly `RADIUS/max(all 12 sampled RADIUS values)`; it must not be relabelled true radius/tube radius without source confirmation.

The reader retains the inventory of excluded response channels, including 96,000 distribution cells, without feeding them into predictors. Dynamic pressure, velocities, dispersed-phase labels, wall temperatures, distributions and unverified power/heat-flux fields do not enter the task. Phase labels check the original frozen stratified allocation only. Changing excluded measurement values cannot alter prediction inputs.

## Disclosed scientific routine

The density inputs are fixed saturation approximations from pressure, not independent density measurements or discovered primitives. The implementation expands equations 1–3 of [IAPWS SR1-86(1992)](https://iapws.org/technical-guidance/release/Supp-sat); the [Wagner–Pruss primary paper](https://srd.nist.gov/jpcrdreprint/1.555926.pdf) provides Appendix Table 1 verification points. Triple-point, normal-boiling-point and critical-point tests match the printed precision. Twelve property evaluations use 80 fixed bisection steps each: 960 iterations, zero fitted parameters and zero target calibrations. The recipe records constants, units, source, inversion range and prior implementation hashes.

The frozen leaderboard complexity counts submitted expressions or trees relative to prepared inputs. It excludes these upstream property operations, calibration and scenario preprocessing. Full-pipeline simplicity remains unassessed. The application and portable HTML now state this scope; no historical metric, Rule Card, score or ranking was rewritten.

## Partitions and dependence

| Partition | Complete runs | Task rows |
|---|---:|---:|
| Train | 7 | 84 |
| Dev | 2 | 24 |
| Test inputs | 3 | 36 |

All 144 sample identities, group identities, partition memberships and numerical values match the frozen public package exactly. The original hash-selected test contains two liquid-labelled runs and one vapor-labelled run; the compact hash allocation selects two remaining dev runs. No response-dependent pruning or new cohort selection occurs.

Four acquisition dates are represented. August 8 and August 10 contain both train and dev runs; August 9 contains train and test runs. Whole-run separation passes the existing declared unit check, but it does not establish independent-day, calibration, apparatus or chronological transfer. This dependence is preserved explicitly rather than silently changing the frozen split.

## Verification and remaining gates

[The native verification receipt](NATIVE_BOILING_VERIFICATION.json) binds all fourteen sources, the reader, numerical runtime and exact public parity. All eight generated artifacts replay byte-for-byte from the isolated installed wheel. The private draft occupies **125,842 expanded bytes / 108,855 stored bytes**. It exports no test targets and opens no evaluator vault.

Thirty-eight new tests cover published property verification, source identity, complete radial panels, units/domains, XML resource/entity guards, fixed phase strata, run/date separation and excluded-response independence. The full suite has **533 passing tests**. Clean installation, twelve CLI paths, numerical fixture, packaged UI/server and HTTP security checks pass. [Browser verification](BOILING_UI_VERIFICATION.json) retains all 13 complete execution attempts, 20 submitted rules and five invalid rule assessments, including Engine rule 1 with 33/36 eligible targets. Engine rule 3 shows 36/36 coverage. Execution completion is not equivalent to valid predictive coverage.

All 693 static Rule Card pages were regenerated while the 4,175 canonical JSON/CSV artifacts remained unchanged. Native reconstruction, replay and interface verification made zero model calls. Source processing, units, dependence, final attribution, scientific contracts and a justified perturbation model remain admission gates. Novelty, mechanism, practical impact and external review remain unassessed.
