# From isolated formulas to connected scientific hypotheses

**Principia-ASD 1.0.0rc5 · local acceptance preview · 15 October 2026**

This iteration addresses repeated rule listings and a search space dominated by scalar polynomial expressions. The deployed rc4 website remains unchanged. The frozen forty-scenario data edition and all 693 primary rules are preserved byte for byte.

## Try the local preview

Open **http://127.0.0.1:8150/** and select **Connected equations** in the scenario library.

1. Open **Polymer relaxation: coupled storage and loss → View explored rules**. Inspect the fractional or multi-mode system. Its intermediate quantities are actual computations, not an illustration placed above a different predictor.
2. Open **connected equations · quantities and assumptions** on the Rule Card. See each quantity's meaning, unit and dependencies, alongside shared parameters and local fit-identifiability diagnostics.
3. Choose **Try it yourself → Scientific equation search** to run the disclosed constitutive families without an API key. Choose **Adaptive Equation Discovery (AED)** for two SiliconFlow proposal/revision rounds guided by executed development diagnostics. New personal runs remain separate from the example leaderboards.
4. Revisit the stellar-flux example. Its 17 submissions now appear in 13 structural groups; the largest group retains three separately fitted submissions. Expand a group to inspect each method, value and receipt.

Grouping does not average scores, erase failures or prove algebraic equivalence. Different fitted parameters can have the same form. Structurally different explanations are retained even when their predictions are close. The raw downloads keep every original record.

## What the engine now represents

An equation system is an ordered graph of measured inputs, explicitly sourced constants, shared fitted parameters and named intermediate quantities. Each equation has a unit and a meaning. The interpreter checks dimensions, dependencies, bounds and complete parameter coverage, and rejects undeclared quantities, target aliases, forward/cyclic references, unused hidden state and unapproved fixed coefficients. It runs a bounded numerical expression language, never generated Python.

For a viscoelastic response, a thermal shift changes the relaxation timescale; dimensionless frequency activates each relaxation mode; elastic storage and viscous loss contributions combine into the requested channel. Fractional powers and phase functions offer a distributed-spectrum alternative. Both channels share one parameter vector. This is joint-response fitting, **not** an independent cross-response confirmation.

**Scientific equation search** fits the sourced alternatives. **AED** additionally asks a model to propose and revise systems using train/dev feedback, fits them locally, and retains a development-selected error/expanded-complexity portfolio. The local pilot uses the exact `deepseek-ai/DeepSeek-V4-Flash` configuration; the UI allows another explicitly checked profile. A run with no successfully fitted model proposal is marked incomplete rather than silently presenting the template search as adaptive discovery.

Limits are 24 equation nodes, eight shared fitted parameters, 16 fits, two model requests, 200 optimizer evaluations per fit, two deterministic starts per candidate, and the existing wall/memory/monetary limits. Actual residual evaluations, optimizer evaluations, restarts, failures and CPU time are recorded separately. Positive parameters use explicit logarithmic optimizer coordinates. Final assessment makes no API calls. Expanded operations and shared DAG operations are both reported; a named intermediate cannot hide complexity.

A useful hypothesis can be simple. Equations are not rewarded merely for being longer or looking physical. Unit consistency checks mathematical admissibility; intermediate meanings, mechanism, novelty and practical value still need scientific assessment.

## Three compact source-aligned additions

| Local scenario | Question and partition | Expanded public package |
|---|---|---:|
| P100-048 · Atmospheric longwave radiation across climates | Temperature and humidity → downwelling longwave irradiance. Desert Rock January trains, July develops; Penn State is the held-out site. | 0.58 MB |
| P100-057 · Resin flow across temperature and shear | Temperature and shear rate → viscosity. Complete native instrument runs remain together: three train, one dev, one test. | 0.30 MB |
| P100-058 · Polymer relaxation: coupled storage and loss | Frequency, temperature and requested response channel → modulus. Complete paired-response temperature sweeps are partitioned. | 0.10 MB |

Native source files were reused locally, with registry identities, source hashes, row coordinates, original units, deterministic SI conversions and explicit exclusion receipts. No raw data were overwritten or downloaded again. Public test files contain inputs only. The separate evaluator holds targets and excluded raw readings. Rebuilding requires the registered local source corpus and `scripts/prepare_equation_pack.py`; it refuses to overwrite an existing edition.

The radiation task retains all weather conditions and discloses its fixed hourly selection and source QC flags. A clear-sky-inspired humidity model can fail under clouds. The resin subset retains noisy positive readings and excludes 38 nonpositive readings by an explicit validity rule; instrument uncertainty is not calibrated. The polymer data cover one batch, use filename temperature set points and have no compliance correction; three invalid frequency/modulus rows are excluded. These are documented research scenarios, not external scientific certifications.

Source records: [NOAA SURFRAD](https://gml.noaa.gov/grad/surfrad/), [rheometer data](https://zenodo.org/records/19699588), [PDLLA measurements](https://zenodo.org/records/17294879). NOAA observations retain their acknowledgment requirement; the two Zenodo sources retain CC BY 4.0 terms.

## Local pilot: all assigned outcomes retained

The separately frozen engineering pilot assigned **3 scenarios × 5 methods = 15 attempts**. It retained **12 complete and three failed executions**, producing **19 rules**. The model completed six paid requests. Every submission froze before any test assessment, and all 15 assessments replay exactly with network access denied and an unchanged ledger.

| Task metric, lower is better | Mean control | Best valid regression control | Best scientific template | Best AED submission |
|---|---:|---:|---:|---:|
| Radiation · MAE, W/m² | 74.4088 | 62.3777 | 46.9174 | 46.9174 |
| Resin · mean absolute log error | 0.887858 | 0.582662 | 0.319542 | 0.313356 |
| Coupled modulus · mean absolute log error | 7.524406 | No valid regression submission | 0.739206 | 0.632808 |

The resin linear control and polymer linear/polynomial controls failed; they are retained in their task denominators. The adaptive radiation portfolio selected the seed gray-atmosphere model rather than its more elaborate proposals. Resin and polymer portfolios include actual model-proposed connected systems, including yield-stress contributions and multiple relaxation branches. These are single-run, retrospective engineering observations without significance, uniqueness or mechanistic-validation claims. Failed candidates and the complete development archive remain in the run records.

The new pilot cost **CNY 0.193098**. Conservative project accounting is **CNY 61.1560825 / 3,000**, including the existing **CNY 24** of unresolved historical reservations. No new unknown reservations remain. A presentation-only static export failure was corrected after assessment; the repair changed no numerical JSON and made no further model calls.

## Files and boundaries

- Source and UI: this project; Python import `principia_asd`, version `1.0.0rc5`.
- New public-data draft: `../collections/equation-pack-v1/data/`.
- New task results: `../collections/equation-pack-v1/leaderboards/` (JSON, CSV, HTML, executable graphs and receipts).
- New protected targets: `../../private-evaluator/ASD-Scenarios-equations-26Oct15/` — never publish.
- Local pack registration: the owner's private workspace `scenario-packs.json`. A pack cannot replace an existing example identity.
- Frozen pilot source, provider receipts and all candidate histories: private `local-campaigns/equation-systems-local-v1/` and its named run directories.

The local library has **43 scenarios**. The original primary comparison remains **520 attempts / 693 rules**; this engineering extension is a separate track. No new public release or deployment is authorized by this iteration.

Scientific priors are explicitly sourced, including [Brutsaert's clear-sky formulation](https://doi.org/10.1029/WR011i005p00742), [generalized Maxwell response](https://pmc.ncbi.nlm.nih.gov/articles/PMC3195339/), and [fractional constitutive models](https://pmc.ncbi.nlm.nih.gov/articles/PMC4658031/). Their reuse provides interpretable model families; it is not evidence of discovering those laws anew.


## Local acceptance checks

The final Python suite passed **1,754 tests**. Ruff, JavaScript syntax, render-contract regressions, twelve installed CLI command interfaces and dependency consistency passed. The clean wheel matches all **118 package files**. A browser-started scientific equation search completed six training fits, froze three rules, evaluated them and displayed the result with **zero model calls**. Its private interactive record is separate from the fifteen-attempt pilot and does not change the shared leaderboard.

Browser testing caught and corrected an equation-evidence rendering mismatch in the run monitor. Distinct forms with the same descriptive name now have readable form numbers; repeated fits expand under their shared form. Model settings and the connected-equation filter were checked. No paid requests were repeated during these fixes.

The acceptance receipt is [LOCAL_ACCEPTANCE_2026-10-15.json](LOCAL_ACCEPTANCE_2026-10-15.json). The installable local preview is [principia_asd-1.0.0rc5-py3-none-any.whl](../dist/principia_asd-1.0.0rc5-py3-none-any.whl). Deployment remains deferred for your acceptance. The new graph methods require explicit unit contracts; existing scalar results retain their original interpretation and are not retrospectively promoted to physical mechanisms.
