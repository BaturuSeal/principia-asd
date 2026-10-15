# P100-084 — AFM force exports and calibration custody

This review adds a private reconstruction draft, not an admitted scenario or a replacement of historical results. The original 40-case edition, all 520 primary attempts and their numerical assessments remain unchanged.

## Source and representation

The registered source is Kanakousaki et al., [Zenodo record 20281797](https://zenodo.org/records/20281797), DOI 10.5281/zenodo.20281797. The retained metadata records CC BY 4.0. The recipe binds three original assets totalling **10,081,425 bytes**: the data ZIP, source README and repository metadata. They remain outside upload roots. Final rights/notice and scientific admission are pending.

The ZIP has 98 members and 8,318,170 expanded bytes. It includes images, binary instrument files and thirteen calibrated force-distance text exports: four Flat, four Low Roughness and five High Roughness curves. This reader decodes all **1,664 rows** of those thirteen six-column exports and checks each paired Bruker instrument header. It does not decode the binary signal payload, reproduce NanoScope processing, interpret images, or reuse fitted modulus and adhesion maps. The source README describes probe calibration and DMT fitting, but no DMT fit or source-derived modulus enters this task.

## Instrument and unit checks

Text columns distinguish calculated approach/retraction ramp coordinates in nm, measured deflection in nm, and calibrated force in pN. Force is converted to nN by division by 1000. All paired headers record a spring constant of **20.7519 N/m**. Both force columns agree with their deflection column times this fixed constant, within text-export rounding tolerances; no coefficient is fitted. Retraction deflection is therefore a direct response alias and is explicitly excluded from predictors.

A calibration-provenance discrepancy remains: the source README reports **86.5 nm/V**, while the paired headers record **68.49950 nm/V** for Flat/Low Roughness and **66.70613 nm/V** for High Roughness. Header force sensitivities agree with the header spring constant and deflection sensitivity. This internal consistency does not establish which calibration is physically correct. Existing exported forces are preserved; no rescaling or retrospective score correction is made. The UI and static Rule Cards carry an advisory bound to the exact historical contract.

Approach coordinates increase and retraction coordinates decrease. Their complementary ramp geometry is verified within export precision. The final retraction coordinate has a small 0.000003755093 nm rounding residual, retained without clipping. These are calculated piezo coordinates, not directly measured indentation or physical acquisition times.

## Permitted calibration and prediction

The entire approach and only the first five retraction samples are available before prediction. The baseline is the mean of the first ten approach force samples. A fixed baseline-plus-5 nN crossing supplies the coordinate origin. Initial retraction amplitude is its first-five mean minus the baseline. Each prediction uses normalized retraction coordinate, baseline, amplitude and ramp-index progress. Targets start at zero-based index 16, physical text row 18, and end at row 129.

The reader retains all **1,456 eligible rows**. It does not select curves or target rows by fit quality, smooth or impute measurements, fit a calibration, or use later retraction force to construct features. Row lineage identifies the exact archive member, physical source row, permitted calibration rows, first threshold-crossing row and paired instrument hash. Test-input tables and lineage contain no test target values. Inputs remain unchanged under paired perturbations of later force and its deflection alias.

| Partition | Whole curves | Task rows |
|---|---:|---:|
| Train | 8 | 896 |
| Dev | 2 | 224 |
| Test inputs | 3 | 336 |

The original hash-selected confirmation curve per surface type is unchanged, as is the compact development allocation. All three surface types appear in both train and test. Curves are locations within the available surface specimens/acquisitions, so this is within-specimen, calibrated curve prediction. It does not establish batch/specimen transfer, material-mechanism identification or a relationship to cell response.

## Verification and release limits

[The reconstruction receipt](NATIVE_AFM_VERIFICATION.json) verifies exact public sample/group identity, unchanged partition membership and zero numeric differences. All eight generated artifacts replay byte-for-byte using isolated Python and the separately installed wheel. The private draft is **424,433 expanded bytes / 261,838 stored bytes**, below the default 10 MB limit. Source files and the frozen edition are unchanged; no evaluator vault, model API or rule fitting is used.

Thirty new regression tests cover physical conversion, exact prefix boundaries, response-alias exclusion, independent late/test-response changes, whole-curve allocation, calibration inconsistencies, schema/units/finite values, ramp domains, rounding preservation, source identity and hashes, paired-file custody and unsafe/oversized archives. The full suite passes **596 tests**. Ruff, JavaScript syntax and cold-install checks pass. [Read-only browser verification](AFM_UI_VERIFICATION.json) confirms the advisory on discovery, the 18-rule/13-attempt leaderboard, the Engine Rule Card and release status. Engine coverage remains 336/336; all four model roles and diagnostic-only sensitivity remain visible. No new inquiry is dispatched.

The finding is a source-provenance limitation, not a fifth established preparation defect. Scientific review, source clarification, physical calibration uncertainty, valid perturbation standards and external assessment remain open. Historical simplicity measures submitted rules relative to prepared inputs; full-pipeline complexity remains unassessed. A future changed calibration or independence contract requires a separately versioned edition and a newly frozen comparison, not edits to existing scores.
