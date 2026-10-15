# Example scenario guide

This edition contains 40 compact examples. These editorial descriptions accompany the frozen task contracts; they do not change their data, metrics, provenance or scientific admission status. There is no minimum scenario-count requirement for release.

Each task has a separate rule leaderboard. Create local input/output variants in the application; they use the existing train/dev partitions and carry no inherited private-test score.

## P100-002 · Stellar brightness over time

TESS satellite light curves record changes in stellar brightness. This example relates recent hourly flux summaries to the next hourly value.

Package: `scenarios/P100-002/`

Task: **Predict next-hour stellar flux**

Independent unit: Star; repeated hourly bins are dependent

| Variable | Role | Definition | Units |
|---|---|---|---|
| lag1 | input | Lagged observation (source window: 1); author-normalized relative flux | author-normalized relative flux |
| lag2 | input | Lagged observation (source window: 2); author-normalized relative flux | author-normalized relative flux |
| lag3 | input | Lagged observation (source window: 3); author-normalized relative flux | author-normalized relative flux |
| lag4 | input | Lagged observation (source window: 4); author-normalized relative flux | author-normalized relative flux |
| lag6 | input | Lagged observation (source window: 6); author-normalized relative flux | author-normalized relative flux |
| lag12 | input | Lagged observation (source window: 12); author-normalized relative flux | author-normalized relative flux |
| lag24 | input | Lagged observation (source window: 24); author-normalized relative flux | author-normalized relative flux |
| median6 | input | Median of preceding observations (source window: 6); author-normalized relative flux | author-normalized relative flux |
| median24 | input | Median of preceding observations (source window: 24); author-normalized relative flux | author-normalized relative flux |
| mad6 | input | Median absolute deviation of the preceding six hourly flux values | author-normalized relative flux |
| target | output | Next hourly median systematics-corrected stellar flux | relative flux (native normalization) |

Scope: Predict next disjoint hourly bin using preceding observed hourly medians only. The released light curve was author-corrected using full-sector information; this is a retrospective product-space forecast, not a raw real-time pipeline.

Original source title: MAST TARS TESS Sector 96 light curves and vetting images

## P100-003 · Gravitational-wave detector noise

Hanford detector strain is summarized over nonoverlapping time windows. Explore relationships between recent spectral noise measurements and the next window’s strain amplitude.

Package: `scenarios/P100-003/`

Task: **Predict next-window strain amplitude**

Independent unit: Contiguous512-second block in one detector segment; blocks not independent experiments

| Variable | Role | Definition | Units |
|---|---|---|---|
| lag1 | input | Lagged observation (source window: 1); RMS strain in units of 1e-21 | RMS strain in units of 1e-21 |
| lag2 | input | Lagged observation (source window: 2); RMS strain in units of 1e-21 | RMS strain in units of 1e-21 |
| lag3 | input | Lagged observation (source window: 3); RMS strain in units of 1e-21 | RMS strain in units of 1e-21 |
| lag4 | input | Lagged observation (source window: 4); RMS strain in units of 1e-21 | RMS strain in units of 1e-21 |
| median4 | input | Median of preceding observations (source window: 4); RMS strain in units of 1e-21 | RMS strain in units of 1e-21 |
| mad4 | input | Median absolute deviation of the preceding four strain windows | RMS strain in units of 1e-21 |
| low1 | input | Previous-window low-band strain amplitude | RMS strain in units of 1e-21 |
| high1 | input | Previous-window high-band strain amplitude | RMS strain in units of 1e-21 |
| line1 | input | Previous-window spectral-line amplitude | RMS strain in units of 1e-21 |
| target | output | Next nonoverlapping16-second recorded 30–80Hz strain RMS | 10^-21 strain |

Scope: Only earlier16-second strain summaries used. Quality masks applied to entire predictor and target windows; no centered filters or future PSD.

Original source title: GWOSC O4a H1 strain and detector-quality masks

## P100-006 · Rydberg-atom radio-frequency sensing

An atomic sensor is driven under different detuning and Rabi-frequency conditions. Investigate how these controls relate to the ion-readout amplitude.

Package: `scenarios/P100-006/`

Task: **Predict ion-readout amplitude**

Independent unit: Entire contiguous probe-Rabi blocks; one vapor cell. No independent atomic-cell replication.

| Variable | Role | Definition | Units |
|---|---|---|---|
| detuning_MHz | input | Optical detuning control | MHz |
| rabi_MHz | input | Radio-frequency Rabi-frequency control | MHz |
| target | output | Ion-readout amplitude | arbitrary units |

Scope: Eight contiguous 30-condition Rabi blocks were used for leave-block-out development; blocks 06 and 09 were reserved. Frequencies and nearby Rabi coordinates are dependent. The task covers only the fixed ±60 MHz spectral neighborhood on one cesium cell.

Original source title: NIST Rydberg atom RF sensing: ionization-current versus optical readout

## P100-012 · Hafnia thin-film X-ray reflectivity

X-ray reflectivity measurements characterize a hafnia-on-silicon wafer. Explore intensity as a function of scattering wavevector, position and disclosed calibration measurements.

Package: `scenarios/P100-012/`

Task: **Predict x-ray reflectivity intensity**

Independent unit: Complete deposition batch is the split unit; wafer is the primary aggregation unit. All positions on a wafer stay together. Three deposition batches develop; fourth confirms.

| Variable | Role | Definition | Units |
|---|---|---|---|
| q | input | Scattering wavevector calculated from X-ray angle | Å⁻¹;4πsin(theta)/lambda |
| q0 | input | Mean wavevector in the disclosed calibration interval | Å⁻¹; calibration mean wavevector |
| I0 | input | Mean intensity near the calibration angle | counts; mean at2theta1.0±0.008deg |
| outer | input | Indicator for a noncentral wafer measurement position | binary noncenter measurement position |
| target | output | native higher-angle XRR intensity | counts |

Scope: Predict higher-angle intensity after measuring a fixed low-angle calibration band of the same spectrum. Position and angle are known acquisition settings.

Original source title: NIST 200 mm hafnia-on-silicon wafer metrology collection

## P100-015 · Household emergency-expense resilience

Public household survey responses describe financial circumstances. This task estimates a reported inability to cover an unexpected expense; it does not identify a causal effect or assess an individual’s creditworthiness.

Package: `scenarios/P100-015/`

Task: **Predict emergency-expense inability**

Independent unit: Respondents nested in whole states; source respondents may share unreported household/environmental dependencies. States not independent populations.

| Variable | Role | Definition | Units |
|---|---|---|---|
| income_proxy | input | Income-bracket midpoint proxy | thousands USD/year bracket proxy |
| household_size | input | Number of household members | persons |
| shock | input | Indicator for no paid or profit work in the previous month; not a job-loss measure | no paid/profit work lastmonth (D1A0) binary, not jobloss |
| age | input | Respondent age | years |
| target | output | Unable to pay hypothetical400USD emergency expense by any listed means | binary EF3_h |

Scope: Contemporaneous2025 household survey association. No future distress observation and no income intervention.

Original source title: Federal Reserve 2025 SHED public-use microdata

## P100-017 · Earthquake depth-estimation uncertainty

Earthquake catalog entries include geometry and quality summaries of the seismic network. Explore their association with the catalog’s reported depth uncertainty.

Package: `scenarios/P100-017/`

Task: **Predict reported depth uncertainty**

Independent unit: Transitive clusters within100km great-circle chord and7days; complete cluster hashfolds. Distant events may still share network/systematic velocity model errors.

| Variable | Role | Definition | Units |
|---|---|---|---|
| depth_km | input | Reported earthquake depth relative to the network reference | km below network reference (may negative) |
| rms_s | input | Reported phase-residual standard error | seconds phase residual standardError |
| phases | input | Number of seismic phases used in the origin solution | used phase count |
| stations | input | Number of stations used in the origin solution | used station count |
| gap_deg | input | Largest station azimuthal gap | largest azimuthal gap degrees |
| dmin_km | input | Nearest-station angular distance converted to kilometres | minimum angular station distance*111.195km/degree |
| target | output | Author-reported origin depth uncertainty | km |

Scope: Contemporaneous reported location-quality diagnostics, never pre-event earthquake forecast or independent true depth error.

Original source title: USGS ComCat July 2026 global M2.5+ earthquakes

## P100-018 · Tornado damage and event geometry

Storm reports pair tornado dimensions and timing with property-damage estimates. Explore empirical damage relationships while retaining reporting and estimate uncertainty.

Package: `scenarios/P100-018/`

Task: **Predict log property-damage estimate**

Independent unit: NOAA EPISODE_ID outbreak groups; nearby episodes may still be correlated or linked across offices. Not individual property samples.

| Variable | Role | Definition | Units |
|---|---|---|---|
| length_km | input | Length km. Recorded definition: km path length | km path length |
| width_km | input | Width km. Recorded definition: km maximum path width | km maximum path width |
| duration_min | input | Duration min. Recorded definition: minutes event duration | minutes event duration |
| latitude | input | Latitude. Recorded definition: degrees north | degrees north |
| month | input | Month. Recorded definition: calendar1–12 | calendar1–12 |
| target | output | Log transformed reported tornado property-damage estimate | ln(1+property damage in USD) |

Scope: Post-event path and timing diagnostic of reported loss. EF damage-derived scale, casualty counts, narratives, monetary/crop losses excluded from predictors.

Original source title: NOAA Storm Events 2025 details, fatalities, and locations

## P100-019 · Vehicle complaint volumes over time

Monthly counts summarize received vehicle complaints by make and model. Explore how past complaint volumes relate to the next month’s reported count.

Package: `scenarios/P100-019/`

Task: **Predict next-month complaint count**

Independent unit: Whole target months; same known vehicle cohorts repeat, lag windows overlap. Three held months are not independent fleets or defect experiments.

| Variable | Role | Definition | Units |
|---|---|---|---|
| lag1 | input | Lagged observation (source window: 1); prior calendar month unique ODINO count | prior calendar month unique ODINO count |
| lag3 | input | Lagged observation (source window: 3); mean prior3monthly counts | mean prior3monthly counts |
| lag6 | input | Lagged observation (source window: 6); mean prior6monthly counts | mean prior6monthly counts |
| month | input | Month. Recorded definition: target calendar month1–12 | target calendar month1–12 |
| target | output | Next-month unique received vehicle complaints per known make/model | complaints/month |

Scope: Only prior-month LDATE received counts predict next month. Retrospective snapshot may revise product labels and records; historical DATEA/report publication lag means calendar causality is not verified as-issued availability. No incident-date future information used.

Original source title: NHTSA complaints, recalls, investigations, and manufacturer communications

## P100-020 · Sea-surface temperature anomaly maps

Satellite-derived ocean temperature anomaly maps provide spatial neighborhoods. Reconstruct a withheld pixel from nearby observations without treating interpolation as a physical mechanism.

Package: `scenarios/P100-020/`

Task: **Predict withheld-pixel temperature anomaly**

Independent unit: Complete20degree geographic tile for scoring; all tiles belong to one dependent global map, not independent temporal replicates.

| Variable | Role | Definition | Units |
|---|---|---|---|
| hx | input | Mean of the immediate horizontal neighbors | °C |
| hy | input | Mean of the immediate vertical neighbors | °C |
| ox | input | Mean of the outer horizontal neighbors | °C |
| oy | input | Mean of the outer vertical neighbors | °C |
| dg | input | Mean of the diagonal neighbors | °C |
| gx | input | Absolute horizontal-neighbor contrast | °C |
| gy | input | Absolute vertical-neighbor contrast | °C |
| clat | input | Cosine of latitude | dimensionless cosine latitude |
| target | output | SST anomaly at a withheld pixel | °C |

Scope: Retrospective reconstruction of one daily map, using twelve fixed neighboring pixels from the same date. Not a future forecast.

Original source title: NOAA Coral Reef Watch global 5 km sea-surface temperature anomaly

## P100-022 · Perovskite memristor forming current

Electrical forming sweeps measure current as voltage increases in lead-free perovskite devices. Compare voltage-response relationships across the recorded composition conditions.

Package: `scenarios/P100-022/`

Task: **Predict forming-sweep current**

Independent unit: Complete device, both compositions; all duplicate device traces linked. No future current or state permitted.

| Variable | Role | Definition | Units |
|---|---|---|---|
| voltage_V | input | Voltage v. Recorded definition: V | V |
| bromine_rich | input | Bromine rich. Recorded definition: indicator | indicator |
| target | output | Initial positive forming-sweep current | microampere |

Scope: A fixed SHA-256 allocation reserved ten complete devices per composition. Development used five hash-assigned device folds. Exact duplicate native traces were linked and deduplicated. The task predicts the initial positive forming branch from voltage and composition alone; no current calibration or later sweep is a predictor.

Original source title: Lead-free perovskite memristors

## P100-023 · Finger-pad friction in viscous liquids

Spreading experiments connect friction with liquid viscosity, motion and contact conditions. Some released descriptors are author-derived calibrations, rather than direct sensor readings.

Package: `scenarios/P100-023/`

Task: **Predict median friction coefficient**

Independent unit: whole participant

| Variable | Role | Definition | Units |
|---|---|---|---|
| H | input | Author-calibrated Hersey descriptor | dimensionless; author Hersey calibration |
| viscosity | input | Author-fitted liquid viscosity at the specified shear rate | Pa s at 500 s^-1; author rheology fit |
| speed | input | Sliding speed | m/s |
| load | input | Normal contact load | N |
| hydration | input | Instrument-reported skin hydration | corneometer instrument units |
| area | input | Contact area | cm^2 |
| target | output | Author-derived median coefficient of friction | dimensionless |

Scope: Conditional prediction at supplied trial-average speed/load. These trial summaries are not prospective controller inputs; no temporal forecasting claim.

Original source title: Finger-pad friction during viscous liquid spreading

## P100-025 · Battery X-ray absorption during cycling

Operando iron-edge absorption spectra track a battery electrode through cycling. Investigate spectral response using disclosed reference spectra and protocol descriptors.

Package: `scenarios/P100-025/`

Task: **Predict iron-edge absorption**

Independent unit: Complete three-acquisitionblock linked to the source3×binnedrepresentation; oneLFPcycleonly. Fivecontiguouschronologicaldevelopmentfolds holdout wholeblocks, withfuturedevelopmentsegments allowed for thisretrospectivecompressiontask.

| Variable | Role | Definition | Units |
|---|---|---|---|
| pre | input | Disclosed pre-edge absorption level | rawμ(E),dimensionless |
| jump | input | Disclosed absorption-edge jump | rawμ(E),dimensionless |
| rL | input | Normalized measured lithium-iron-phosphate reference | normalizedmeasuredLiFePO4reference |
| rF | input | Normalized measured iron-phosphate reference | normalizedmeasuredFePO4reference |
| dL | input | First energy derivative of the lithium-iron-phosphate reference | eV⁻¹ |
| d2L | input | Second energy derivative of the lithium-iron-phosphate reference | eV⁻² |
| f | input | Nominal protocol progress | dimensionlessnominalprotocolprogress |
| discharge | input | Discharge branch indicator | binarydischarge/rest2branch |
| rest | input | Rest segment indicator | binaryrestsegment |
| e | input | Energy relative to the iron-edge reference | eVrelative7112 |
| target | output | raw measured FeK-edge μ(E) | dimensionless μ(E) |

Scope: Retrospective spectral-shape reconstruction after pre/post-edge calibration bands and experimental segment durations are known. This is not an online state-of-charge forecast.

Original source title: Operando XAS and battery electrochemistry

## P100-026 · Catalyst selectivity over time

Silver-zeolite experiments track dimethoxymethane selectivity during reaction. Explore changes after disclosed early calibration measurements at different silver loadings.

Package: `scenarios/P100-026/`

Task: **Predict dimethoxymethane selectivity**

Independent unit: Complete reactor run. Diagnostic forecast after 300 min with fixed prefix calibration; no future conversion/selectivity predictors.

| Variable | Role | Definition | Units |
|---|---|---|---|
| elapsed_min | input | Elapsed min. Recorded definition: min | min |
| anchor_selectivity_pct | input | Anchor selectivity pct. Recorded definition: percent | percent |
| prefix_slope_pct_min | input | Prefix slope pct min. Recorded definition: percent/min | percent/min |
| ag_wt_pct | input | Ag wt pct. Recorded definition: wt percent | wt percent |
| target | output | Dimethoxymethane selectivity | percentage points |

Scope: Six complete reactor runs were developed with leave-run-out validation; the 220°C-labelled and calcined-catalyst runs were reserved. All models receive the same fixed 300-minute calibration prefix. The long-term figure duplicated in the source is counted once. No instantaneous conversion or other selectivity enters the predictor.

Original source title: Silver zeolite methanol dehydrogenation experiments

## P100-027 · Vapor distribution in boiling-water flow

Two-phase water-flow experiments measure local vapor void fraction. Relate radial position and operating conditions to this measured distribution.

Package: `scenarios/P100-027/`

Task: **Predict local vapor void fraction**

Independent unit: complete experimental run

| Variable | Role | Definition | Units |
|---|---|---|---|
| pressure_Pa | input | Pressure pa. Recorded definition: Pa, absolute | Pa, absolute |
| massflux_kg_m2_s | input | Massflux kg m2 s. Recorded definition: kg m^-2 s^-1 | kg m^-2 s^-1 |
| quality | input | Quality. Recorded definition: kg vapor per kg mixture | kg vapor per kg mixture |
| radial_fraction | input | Radial fraction. Recorded definition: dimensionless native coordinate / maximum sampled coordinate | dimensionless native coordinate / maximum sampled coordinate |
| rho_liquid | input | Rho liquid. Recorded definition: kg m^-3 | kg m^-3 |
| rho_vapor | input | Rho vapor. Recorded definition: kg m^-3 | kg m^-3 |
| target | output | Measured local vapor void fraction | dimensionless |

Scope: Boundary pressure, mass flux, supplied thermodynamic quality, density properties and measurement coordinate only; no measured target-derived velocity, dynamic pressure, phase label or fitted per-run offset.

Original source title: KTH boiling two-phase water flow

## P100-028 · Parametric microwave scattering

Pump-controlled microwave experiments measure an off-diagonal sideband response. Use disclosed low-pump calibrations and frequency separation to investigate the response magnitude.

Package: `scenarios/P100-028/`

Task: **Predict sideband response magnitude**

Independent unit: Completepumpstrengthmatrix; all156offdiagonaldirectedpairslinked. Oneinstrument/day; strengthlevels are not independent devices.

| Variable | Role | Definition | Units |
|---|---|---|---|
| lo | input | Low-pump calibration response | fsu;lowpumpamplituderesponse |
| hi | input | Second disclosed calibration response | fsu;secondcalibrationresponse |
| noise | input | Zero-pump response | fsu;zero-pumpresponse |
| r | input | Normalized pump increment | dimensionless normalizedpumpincrement |
| g | input | Pump-amplitude control | fsu;pumpamplitudecontrol |
| glo | input | Low calibration pump control | fsu;lowpumpcontrol |
| ghi | input | High calibration pump control | fsu;highcalibrationpumpcontrol |
| sep | input | Frequency-bin separation | integer frequency-bin separation;100kHzbins |
| target | output | magnitude of native complex USB off-diagonal response | fsu; instrument full-scale units |

Scope: Predict conversion response above the two calibration pump strengths; each directedmodepair is calibrated at0,.13,.1402040816pumpunits. Whole strongerpumpmatrices are reserved, not selected edges.

Original source title: Inverse parametric microwave scattering

## P100-030 · Friction with boron-nitride lubricants

Lubricant tests measure friction across sliding speeds and additive concentrations. Explore the intermediate response using disclosed boundary and high-speed calibrations.

Package: `scenarios/P100-030/`

Task: **Predict friction coefficient**

Independent unit: Material formulation, repeated representations linked. Two-point calibration at 0.2 and500 mm/s; score0.28–10 mm/s.

| Variable | Role | Definition | Units |
|---|---|---|---|
| speed_mm_s | input | Speed mm s. Recorded definition: mm/s | mm/s |
| boundary_cof | input | Boundary cof. Recorded definition: dimensionless | dimensionless |
| highspeed_cof | input | Highspeed cof. Recorded definition: dimensionless | dimensionless |
| concentration_wt_pct | input | Concentration wt pct. Recorded definition: wt percent | wt percent |
| target | output | Coefficient of friction | dimensionless |

Scope: Six formulations were developed with leave-formulation-out validation; N+S functionalization and NG supplier curves were reserved. Duplicate curves cannot cross partitions. Both endpoint calibrations are provided for every curve. Scoring covers only 0.28–10 mm/s and tests calibrated shape transfer, not unmeasured-lubricant performance.

Original source title: Particle size and surface modification of hBN lubricants

## P100-031 · Quantum-circuit compilation time

Circuit benchmarks compare compilation tools. Investigate wall time using circuit size and an observed Qiskit pilot; this is conditional on the pilot’s computational cost.

Package: `scenarios/P100-031/`

Task: **Predict mean compilation time**

Independent unit: Circuit family after stripping numeric size suffixes; compiler observations on each family stay linked. One local CPU family; no independent hardware transfer.

| Variable | Role | Definition | Units |
|---|---|---|---|
| pilot_seconds | input | Pilot seconds. Recorded definition: seconds Qiskit calibration cost | seconds Qiskit calibration cost |
| qubits | input | Qubits. Recorded definition: input qubit count | input qubit count |
| pilot_gates | input | Pilot gates. Recorded definition: Qiskit output two-qubit gate count | Qiskit output two-qubit gate count |
| pilot_depth | input | Pilot depth. Recorded definition: Qiskit output two-qubit depth | Qiskit output two-qubit depth |
| load_seconds | input | Load seconds. Recorded definition: Qiskit QASM loading seconds | Qiskit QASM loading seconds |
| is_tket | input | Is tket. Recorded definition: SDK indicator | SDK indicator |
| is_bqskit | input | Is bqskit. Recorded definition: SDK indicator,elseStaq | SDK indicator,elseStaq |
| target | output | Author-benchmarked mean compilation wall time after matched Qiskit pilot | seconds |

Scope: Must execute the complete Qiskit pilot first; its runtime and resulting circuit statistics are known only afterward. Candidate SDK timing is withheld. Pilot cost is not free. This is runtime diagnostics, not pre-compilation prediction or quantum-device performance.

Original source title: Quantum circuit compilation benchmark experiments

## P100-032 · Short-horizon respiratory pressure

Respiratory recordings contain gauge and differential pressure channels. Explore short-horizon prediction from past samples and recorded trial conditions; no clinical decision claim is implied.

Package: `scenarios/P100-032/`

Task: **Predict pressure 200 ms ahead**

Independent unit: participant

| Variable | Role | Definition | Units |
|---|---|---|---|
| p0 | input | Gauge pressure 0 samples before the prediction origin | cm H₂O |
| p05 | input | Gauge pressure 5 samples before the prediction origin | cm H₂O |
| p10 | input | Gauge pressure 10 samples before the prediction origin | cm H₂O |
| p20 | input | Gauge pressure 20 samples before the prediction origin | cm H₂O |
| p30 | input | Gauge pressure 30 samples before the prediction origin | cm H₂O |
| p40 | input | Gauge pressure 40 samples before the prediction origin | cm H₂O |
| p50 | input | Gauge pressure 50 samples before the prediction origin | cm H₂O |
| di0 | input | Current inspiratory differential pressure | cm H₂O |
| de0 | input | Current expiratory differential pressure | cm H₂O |
| di20 | input | Inspiratory differential pressure 20 samples before the prediction origin | cm H₂O |
| de20 | input | Expiratory differential pressure 20 samples before the prediction origin | cm H₂O |
| trial_BH | input | Source PEEP_BH trial indicator | binary |
| trial_FEM | input | Source FEM trial indicator | binary |
| target | output | gauge_pressure_200ms_future | cm H₂O |

Scope: At each fixed1s origin predict native gauge pressure0.20s later using only present/past pressure and differential-pressure signals.

Original source title: CPAP respiratory pressure measurements

## P100-033 · Heart rate from smartphone pulse signals

Phone photoplethysmography is compared with ECG reference heart rate. Explore how spectral, autocorrelation and acquisition-quality descriptors predict the reference rate.

Package: `scenarios/P100-033/`

Task: **Predict ecg reference heart rate**

Independent unit: Person; every recording from one person linked

| Variable | Role | Definition | Units |
|---|---|---|---|
| fft_bpm | input | Heart-rate estimate from the dominant spectral peak | bpm |
| acf_bpm | input | Heart-rate estimate from autocorrelation | bpm |
| half_bpm | input | Half-frequency candidate heart-rate estimate | bpm |
| half_strength | input | Relative spectral power near the half-frequency candidate | dimensionless |
| spectral_quality | input | Spectral concentration quality descriptor | dimensionless |
| agreement | input | Difference between candidate heart-rate estimates | bpm |
| motion | input | Recorded motion-condition descriptor | dimensionless |
| ear | input | Ear recording-site indicator | dimensionless |
| target | output | ECG reference heart rate | bpm |

Scope: After the complete ten-second PPG segment; simultaneous ECG supplies the target but is never an input. Known recording motion/contact conditions are allowed. No human quality annotation is a predictor.

Original source title: Smartphone PPG with ECG reference and acquisition disturbances

## P100-035 · Animal vocalization and recording context

Ungulate vocalizations are represented by acoustic descriptors and source context labels. Explore associations with the recorded context, without inferring an animal’s emotional state.

Package: `scenarios/P100-035/`

Task: **Predict positive-context label probability**

Independent unit: Animal within species; all calls and typo-linked names grouped

| Variable | Role | Definition | Units |
|---|---|---|---|
| log_duration | input | Logarithm of recording duration | dimensionless |
| log_centroid | input | Logarithm of spectral centroid | dimensionless |
| log_peak | input | Logarithm of peak frequency | dimensionless |
| high_share | input | High-frequency energy share | dimensionless |
| entropy | input | Spectral entropy | dimensionless |
| flatness | input | Spectral flatness | dimensionless |
| envelope_cv | input | Coefficient of variation of the amplitude envelope | dimensionless |
| log_modulation | input | Logarithm of modulation descriptor | dimensionless |
| log_rms | input | Logarithm of root-mean-square amplitude | dimensionless |
| species_code | input | Source species category encoded numerically; not an ordered biological scale | dimensionless |
| target | output | Source positive-context label probability | probability |

Scope: After the complete author-extracted call. Predictors only waveform summaries and known species. File context words, animal ID, call label and source reference are never predictors.

Original source title: Ungulate vocalizations and production context

## P100-036 · Plant fluorescence under stress

Tomato phenotyping combines fluorescence, image-derived descriptors and treatment indicators. Explore relationships with the author-reported maximum quantum yield.

Package: `scenarios/P100-036/`

Task: **Predict maximum quantum yield**

Independent unit: Plant; repeated sampling remains linked

| Variable | Role | Definition | Units |
|---|---|---|---|
| npq | input | Author-reported steady-state nonphotochemical quenching | dimensionless author NPQ_Lss |
| rfd | input | Author-reported fluorescence decline ratio | dimensionless author Rfd_Lss |
| ngrdi | input | Normalized green-red difference image index | dimensionless RGB index |
| area | input | Source plant-area descriptor; physical scale requires source review | source AREA_MM scale; only relative/log descriptor used |
| tiny | input | Cultivar indicator | cultivar indicator |
| salt | input | Salt-treatment indicator | salt-treatment indicator |
| drought | input | Drought-treatment indicator | drought-treatment indicator |
| high_stress | input | Second source stress-level indicator | source second stress-level indicator; no invented dose units |
| target | output | Author QY_max | dimensionless quantum yield |

Scope: Contemporaneous imaging diagnostic: source NPQ_Lss, Rfd_Lss, NGRDI, morphology and known cultivar/treatment predict separately reported maximum quantum yield. No QY_max-derived feature or future plant measurement is supplied.

Original source title: Dwarf tomato stress imaging and phenotypic measurements

## P100-039 · Education, age and earnings categories

Adult-skills survey data from the USA and Japan connect education and age with earnings categories. The response is a country-relative earnings category, not an absolute wage.

Package: `scenarios/P100-039/`

Task: **Predict upper-earnings-category membership**

Independent unit: Respondents nested in country and deterministic ten hashblocks; not10 independent samples from plausible values. Repeated respondent information stays linked. Survey clustering not publicly fully reconstructible.

| Variable | Role | Definition | Units |
|---|---|---|---|
| education | input | Source-derived years of formal education | source derived years of formal education |
| age | input | Fixed midpoint of a published age bin | fixed midpoint of published five-year age bin; final60–65midpoint62.5 |
| japan | input | Japan survey indicator | country indicator |
| target | output | Upper three country-specific hourly-earnings deciles, excluding bonuses | binary EARNHRDCLC2>=8 |

Scope: Contemporaneous cross-sectional earnings association using age/education/country. All10 plausible numeracy values are excluded: conditioned on background and unsuitable individual prediction scores. This is not future earnings or causal education return.

Original source title: Adult skills, workplace use and earnings in USA and Japan

## P100-043 · Language-model training loss trajectories

Gemstones training runs record validation loss as compute accumulates. Explore later loss using architecture size and disclosed early checkpoints.

Package: `scenarios/P100-043/`

Task: **Predict later validation loss**

Independent unit: complete architecture

| Variable | Role | Definition | Units |
|---|---|---|---|
| tokens_B | input | Training tokens at the prediction checkpoint | billions of training tokens |
| anchor_tokens_B | input | Tokens at the disclosed anchor checkpoint | billions of training tokens |
| early_tokens_B | input | Tokens at the earlier disclosed checkpoint | billions of training tokens |
| anchor_loss | input | Validation loss at the anchor checkpoint | nats per token |
| early_loss | input | Validation loss at the earlier checkpoint | nats per token |
| params_B | input | Language-model parameter count | billions of parameters |
| width | input | Embedding width | embedding dimensions |
| depth | input | Number of model layers | layers |
| target | output | hot-run validation log-perplexity at20–100B tokens | nats per token |

Scope: Only checkpoints at or before10B/20B tokens may calibrate the20–100B forecast

Original source title: Gemstones language-model training trajectories

## P100-045 · Gamma-ray burst spectral count rates

Fermi GBM detector channels record a gamma-ray burst. Explore a higher-energy channel’s count rate using lower-energy channels, background and detector calibration.

Package: `scenarios/P100-045/`

Task: **Predict channel-4 count rate**

Independent unit: Detector within one GRB; detectors share one incident event

| Variable | Role | Definition | Units |
|---|---|---|---|
| low | input | Current count rate in lower-energy channels 2 and 3 | counts/s in channels 2+3 |
| low_lag | input | Lower-energy count rate in the preceding time bin | counts/s in preceding bin, channels 2+3 |
| background_low | input | Pre-trigger background in lower-energy channels | counts/s in pretrigger channels 2+3 |
| background_high | input | Pre-trigger background in channel 4 | counts/s in pretrigger channel 4 |
| time_s | input | Elapsed time after the burst trigger | s after trigger |
| channel_low_keV | input | Lower bound of the response energy channel | keV |
| channel_high_keV | input | Upper bound of the response energy channel | keV |
| target | output | GBM NaI channel4 count rate during fixed post-trigger window | counts/s |

Scope: Same-bin channel2+3 count rates and previous-bin low-energy rate permitted; targetchannel4 observations aftertrigger forbidden as predictors.

Original source title: Fermi GBM GRB250206A spectra and responses

## P100-049 · Battery voltage relaxation

Lithium-graphite cell experiments record voltage after a current pulse. Investigate the relaxation curve using early voltage anchors and pulse conditions.

Package: `scenarios/P100-049/`

Task: **Predict relaxation voltage**

Independent unit: Complete rest block linked to preceding current pulse; all blocks belong to one half-cell, so block summaries are not independent-cell confidence.

| Variable | Role | Definition | Units |
|---|---|---|---|
| t | input | Elapsed time during current-free relaxation | s |
| t60 | input | Actual time of the disclosed 60-second anchor | s |
| t120 | input | Actual time of the disclosed 120-second anchor | s |
| u60 | input | Voltage at the 60-second anchor | V |
| u120 | input | Voltage at the 120-second anchor | V |
| u10 | input | Voltage at the 10-second anchor | V |
| pulse_s | input | Duration of the preceding current pulse | s |
| current | input | Current during the preceding pulse | A |
| target | output | voltage during current-free relaxation | V |

Scope: Issue predictions at120s of each current-free block; only actual samples at or before10/60/120s and completed preceding current pulse are predictors. Targets are nearest native samples to300/600/1200/1800s, tolerance15s.

Original source title: DLR lithium-graphite cell GITT and quasi-open-circuit measurements

## P100-051 · Gate response in semiconductor memories

Patterned metal–semiconductor memory devices are measured across gate voltage. Reconstruct drain current between three disclosed calibration anchors for each response curve.

Package: `scenarios/P100-051/`

Task: **Predict drain current**

Independent unit: complete source FET column/device

| Variable | Role | Definition | Units |
|---|---|---|---|
| gate_V | input | Applied gate voltage | V |
| cal_minus20_uA | input | Drain-current calibration at −20 V | µA |
| cal_zero_uA | input | Drain-current calibration at 0 V | µA |
| cal_plus20_uA | input | Drain-current calibration at +20 V | µA |
| target | output | measured drain current between three disclosed gate-voltage calibration anchors | µA |

Scope: offline sparse-characterization task: three responses at -20,0,20 V are obtained before reconstructing other gate points; not an uncalibrated or causal sweep forecast

Original source title: Data set for "Non-volatile memories based on patterned metal–semiconductor heterostructures of niobium disulfide and molybdenum disulfide"

## P100-053 · Torque during industrial screw driving

Screw-driving cycles record torque over angle and repeated tool use. Relate early-cycle measurements and permitted past-cycle information to later thread-forming torque.

Package: `scenarios/P100-053/`

Task: **Predict thread-forming torque**

Independent unit: workpiece (both locations and every reuse cycle)

| Variable | Role | Definition | Units |
|---|---|---|---|
| early | input | Early-cycle torque summary | Nm |
| finding | input | Screw-finding torque summary | Nm |
| gradient_proxy | input | Early torque-gradient proxy | Nm |
| roughness | input | Early torque fluctuation descriptor | Nm |
| usage | input | Accumulated tool-use cycle count | cycle count |
| left | input | Source left-side indicator | binary indicator |
| has_history | input | Whether a previous cycle is available | binary indicator |
| prev_y | input | Previous permitted cycle’s response torque | Nm |
| prev_early | input | Previous cycle’s early torque | Nm |
| prev_gradient | input | Previous cycle’s torque-gradient proxy | Nm |
| first_y | input | First disclosed cycle’s response torque | Nm |
| mean_past_y | input | Mean response over permitted past cycles | Nm |
| history_gap | input | Gap in cycles since the previous observation | cycle count |
| target | output | Angle-mean thread-forming torque, 700–1300 degrees | Nm |

Scope: Current measurements stop at the frozen first-forward-crossing prefix (first sampled angle at/above 250 degrees); prior responses only from completed same-hole operations. Both holes and every reuse of a workpiece stay together.

Original source title: Industrial screw driving dataset collection: Time series data for process monitoring and anomaly detection

## P100-054 · Microfracture load and notch geometry

Microscale cantilevers with bridge notches are tested to failure. Explore how reported specimen dimensions relate to the second bridge’s failure load.

Package: `scenarios/P100-054/`

Task: **Predict second-bridge failure load**

Independent unit: Cantilever specimen; one source wafer and manufacturing campaign

| Variable | Role | Definition | Units |
|---|---|---|---|
| width_um | input | Cantilever specimen width | µm |
| thickness_um | input | Cantilever specimen thickness | µm |
| length_um | input | Cantilever specimen length | µm |
| notch_depth_um | input | Bridge-notch depth | µm |
| notch_width_um | input | Bridge-notch width | µm |
| target | output | second bridge failure load Pb2 | mN |

Scope: Predict measured second-bridge failure load conditional on reported SEM geometry; geometry may be measured post-test, so this is retrospective geometry-conditioned response, not pre-test control.

Original source title: Data set: Enhanced crack stability in micro scale fracture testing via optimized bridge notches

## P100-055 · Penetration resistance of printable concrete

Slag-based printable mixtures are tested by penetration. Explore normal force across mix-design descriptors, material age and the source penetration clock.

Package: `scenarios/P100-055/`

Task: **Predict penetration normal force**

Independent unit: whole mixture across both ages and replicates

| Variable | Role | Definition | Units |
|---|---|---|---|
| ratio | input | Mix-design ratio encoded in the source mixture label | mix-design ratio encoded in author mixture label |
| water | input | Water ratio encoded in the source mixture label | water ratio encoded in author mixture label |
| age_min | input | Time since mixing | min since mixing; 0 or 30 |
| time_s | input | Source penetration clock index; seconds are not independently established | native penetration clock index; unit unspecified |
| target | output | Individual penetration normal force | N |

Scope: Known mix label, age and elapsed penetration index only; force is never an input.

Original source title: CARBCOMN - Dataset of Early Research Outcomes - Mix Design of 3D-printable Mixes Based on Industrial Slags

## P100-062 · Hydrogen permeation through steel

Electrochemical permeation tests record the anodic current response of high-strength steel. Explore transient response after imposed cathodic-current steps.

Package: `scenarios/P100-062/`

Task: **Predict anodic permeation current**

Independent unit: Two chronological traces with no independent specimen identifiers; nonoverlapping temporal blocks are scoring units, not independent specimens. All trace linkage is explicit.

| Variable | Role | Definition | Units |
|---|---|---|---|
| t | input | Time since the third baseline observation | s since third baseline observation |
| offset | input | Mean of the first three anodic-current observations | μA; mean first3 observations |
| drive | input | Imposed cathodic-current step | mA/cm²; imposed cathodic-current step |
| high | input | Known high-current condition indicator | binary known high-current condition |
| target | output | measured anodic permeation current | μA |

Scope: Forward extrapolation within two linked permeation traces. Parameters are learned only from earlier chronological blocks; confirmation is the last20% of each trace. Known imposed current step and initial three-point current calibration are permitted.

Original source title: Hydrogen permeation test on MS AHSS grade 1300

## P100-068 · Acoustic levitation dynamics

Laser Doppler vibrometer recordings track an acoustically levitated object. Explore short-horizon voltage evolution from recent, offset-corrected observations.

Package: `scenarios/P100-068/`

Task: **Predict ldv voltage 5 ms ahead**

Independent unit: Complete acquisitiontrace, with raw/denoised pair linked; sixmetadata-hashselectedtracesconfirm. Alltraces shareone levitator/object setup.

| Variable | Role | Definition | Units |
|---|---|---|---|
| y0 | input | Current LDV voltage minus the initial offset | V; currentrawminusinitialoffset |
| y1 | input | LDV voltage at the 5 ms lag minus offset | V;5mslagminusoffset |
| y2 | input | LDV voltage at the 10 ms lag minus offset | V;10mslagminusoffset |
| y3 | input | LDV voltage at the 15 ms lag minus offset | V;15mslagminusoffset |
| offset | input | Mean of the first 20 voltage samples | V; first20samplemean |
| t | input | Stored observation timestamp | s; storedtimestamp |
| target | output | raw LDV voltage5ms ahead | V |

Scope: Predict raw voltage5ms ahead using up to15ms of causal delay samples and a fixed initial20sampleoffset. Issue every5ms after50ms; no future filtering.

Original source title: Sparse identification of nonlinear dynamics applied to the levitation of acoustically large objects

## P100-070 · Magnetic maps of laboratory fault heating

Magnetic microscopy maps characterize specimens from laboratory slip experiments. Reconstruct a withheld map ordinate from nearby values; the source-native unit remains unresolved.

Package: `scenarios/P100-070/`

Task: **Predict withheld-pixel magnetic ordinate**

Independent unit: Two specimens: CSH/119DOA development and CSL/129DOA confirmation. Spatial blocks balance errors but are not independent specimens; development folds are entire200row strips.

| Variable | Role | Definition | Units |
|---|---|---|---|
| hx | input | Mean of immediate horizontal neighbors | source-native Bz unit |
| hy | input | Mean of immediate vertical neighbors | source-native Bz unit |
| ox | input | Mean of outer horizontal neighbors | source-native Bz unit |
| oy | input | Mean of outer vertical neighbors | source-native Bz unit |
| dg | input | Mean of diagonal neighbors | source-native Bz unit |
| gx | input | Horizontal contrast normalized by local RMS amplitude | dimensionless local contrast |
| gy | input | Vertical contrast normalized by local RMS amplitude | dimensionless local contrast |
| lo | input | Minimum neighboring ordinate | source-native Bz unit |
| hi | input | Maximum neighboring ordinate | source-native Bz unit |
| target | output | native Bz map ordinate at a withheld pixel | source-native Bz unit (SI conversion unresolved) |

Scope: Retrospective reconstruction at one microscopy acquisition; all neighboring measurements are available. No prediction of an earthquake or temperature history.

Original source title: Imaging Localized Slip-induced Frictional Heating during Laboratory Earthquakes Using Magnetic Microscopy

## P100-072 · Yeast competition in co-culture

Wine-yeast co-cultures are followed by author-reported qPCR composition estimates. Explore later species proportions from two disclosed early measurements.

Package: `scenarios/P100-072/`

Task: **Predict later yeast species percentage**

Independent unit: whole co-cultured strain including every replicate/time

| Variable | Role | Definition | Units |
|---|---|---|---|
| p22_pct | input | Same-replicate species percentage at 22 hours | percentage points; own replicate at22h |
| p72_pct | input | Same-replicate species percentage at 72 hours | percentage points; own replicate at72h |
| time_h | input | Time since inoculation | h since inoculation |
| target | output | Later author qPCR S.kudriavzevii percentage | percentage points |

Scope: Author cached spreadsheet percentage from same-row qPCR ratio is the target. No same-time Cp/ratio is a predictor. Use only own replicate22/72-hour percentages to forecast96h and later. Biological replicate pairing from Sample Name.

Original source title: dataset of the data obtained for publication: Saccharomyces cerevisiae wine strains show a wide range of competitive abilities and differential nutrient uptake behavior in co-culture with S. kudriavzevii

## P100-074 · Kinase biosensor fluorescence kinetics

A biosensor experiment records fluorescence over time at different concentrations. Investigate the kinetic response using early fluorescence calibration and curvature.

Package: `scenarios/P100-074/`

Task: **Predict kinetic fluorescence**

Independent unit: Complete dose curves; seven development and two hash-selected confirmation doses; leave-one-dose-out validation. No biological replicate identifiers.

| Variable | Role | Definition | Units |
|---|---|---|---|
| concentration_uM | input | Source assay concentration | µM |
| time_min | input | Reaction time | min |
| calibration_F6 | input | Disclosed early fluorescence anchor | source fluorescence units |
| calibration_v6 | input | Disclosed early fluorescence slope | source fluorescence units/min |
| calibration_curvature | input | Disclosed early curvature of the fluorescence trace | source fluorescence units/min^2 |
| target | output | Src kinetic fluorescence in source instrument units | source fluorescence units |

Scope: Predict all t>7.5 min from source dose and same-curve measurements at 3,4.5,6 min. Calibration fixed at6 min; no later response access.

Original source title: Dataset from "A triangulenum-based biosensor platform for mapping kinase activity in T cells"

## P100-076 · Neuronal firing and substrate conditions

Stimulation experiments record evoked spike counts under substrate-stiffness and knockdown conditions. Explore conditional response after disclosed within-cell calibration.

Package: `scenarios/P100-076/`

Task: **Predict evoked spike count**

Independent unit: complete culture dish within recording date

| Variable | Role | Definition | Units |
|---|---|---|---|
| current | input | Applied stimulation current | pA |
| soft | input | Soft-substrate condition indicator | binary |
| kd | input | Knockdown condition indicator | binary |
| cal_mean | input | Mean spike count in the disclosed calibration stimuli | spikes per stimulus |
| cal_last | input | Spike count in the last disclosed calibration stimulus | spikes per stimulus |
| target | output | evoked_spike_count | spikes per stimulus |

Scope: Predict higher-current evoked spike counts after the lower-current prefix for that cell. No future rheobase or peak-response calibration.

Original source title: Dataset accompanying the paper "Environmental stiffness regulates neuronal maturation via Piezo1-mediated TTR activity"

## P100-084 · Cellulose biointerface force curves

Atomic-force microscopy measures retraction force at a cellulose-acetate interface. Explore curve shape using calibrated position and initial force measurements.

Package: `scenarios/P100-084/`

Task: **Predict retraction force**

Independent unit: Complete approach/retraction curve is held together; one hashselectedcurveper surface type confirms. Curves are locations on three samples, not independentmanufacturingbatches.

| Variable | Role | Definition | Units |
|---|---|---|---|
| x | input | Normalized piezo position relative to the fixed approach-force crossing | dimensionless normalized piezo position relative to fixed5nNapproach crossing |
| base | input | Mean force in the first ten approach observations | nN; mean first10approachpoints |
| amp | input | Initial retraction force minus the baseline | nN; initialretractionlevel minusbase |
| progress | input | Fraction of the retraction ramp | dimensionless fraction ofretractionramp |
| target | output | native AFM retraction force | nN |

Scope: Predict late retraction after the entire approach and firstfive retraction samples are available. Targets begin at retractionindex16. Measured retraction deflection is excluded because it algebraically determines force.

Original source title: Experimental dataset on Microstructured cellulose acetate biointerfaces regulate mesenchymal stem cell response and promote osteogenic commitment

## P100-086 · Fermentation potency over time

Erythromycin fermentation batches include periodic potency assays. Explore a six-hour forecast using the latest measurement and its past slope.

Package: `scenarios/P100-086/`

Task: **Predict potency six hours ahead**

Independent unit: whole production batch; chronologically latest 81 reserved

| Variable | Role | Definition | Units |
|---|---|---|---|
| time_h | input | Time since cultivation began | h since cultivation, source hh |
| current | input | Last available potency assay | source potency unit; last available potency measurement |
| slope6 | input | Potency slope over the strictly preceding six hours | source potency unit/h from strictly past 6 h |
| target | output | Chemical potency six hours ahead | source potency unit (undocumented) |

Scope: Strictly causal potency history and cultivation clock. Matching plus/minus 6 h uses source clock; future values only become targets.

Original source title: Erythromycin fermentation process dataset

## P100-087 · Cooperation in asymmetric public-goods games

Repeated economic games record individual contributions and partner behavior. Explore the next contribution using only prior rounds and declared game conditions.

Package: `scenarios/P100-087/`

Task: **Predict next-round contribution**

Independent unit: Complete first-session interacting pair;20% hash heldout in each treatment; remaining groups in5 deterministic whole-pair folds. Both players remain together.

| Variable | Role | Definition | Units |
|---|---|---|---|
| round | input | Game round being predicted | round |
| own_previous | input | Participant contribution in the previous round | experimental tokens |
| peer_previous | input | Partner contribution in the previous round | experimental tokens |
| own_lag2 | input | Participant contribution two rounds earlier | experimental tokens |
| peer_lag2 | input | Partner contribution two rounds earlier | experimental tokens |
| own_history_mean | input | Mean participant contribution over prior rounds | experimental tokens |
| peer_history_mean | input | Mean partner contribution over prior rounds | experimental tokens |
| endowment | input | Participant token endowment | experimental tokens |
| peer_endowment | input | Partner token endowment | experimental tokens |
| productivity | input | Participant contribution multiplier | dimensionless |
| peer_productivity | input | Partner contribution multiplier | dimensionless |
| threshold | input | Group success threshold in productivity-weighted tokens | productivity-weighted tokens |
| previous_success | input | Whether the previous round achieved its threshold | indicator |
| required_contribution | input | Contribution requirement derived from the declared game conditions | experimental tokens |
| target | output | Next-round individual contribution | experimental tokens |

Scope: One-step prediction before round3..20 using strictly prior own/peer contributions and publicly announced rules. Earlier confirmation responses are permitted causal online history, never fitted parameters. Surveys and session2 excluded.

Original source title: Dataset and computer code for "The dynamics of cooperation in asymmetric public goods games"

## P100-089 · Risk-taking across ages and contexts

Choice experiments vary reward, probability and presentation context. Explore recorded risky choices using participant descriptors and permitted past-choice summaries.

Package: `scenarios/P100-089/`

Task: **Predict risky choice**

Independent unit: participant

| Variable | Role | Definition | Units |
|---|---|---|---|
| reward | input | Offered risky-option reward | points |
| probability | input | Offered reward probability | probability |
| child | input | Child participant indicator | binary |
| age_child | input | Child age; adult rows use the source sentinel | years; adult sentinel0 |
| multi | input | Multiple-option context indicator | binary |
| description | input | Description-based presentation indicator | binary |
| trial_progress | input | Trial index divided by 40 | trial index/40 |
| lag_choice | input | Prior risky choice, with a first-trial prior | binary or first-trial prior0.5 |
| history_mean | input | Mean prior risky-choice rate, with a first-trial prior | proportion or first-trial prior0.5 |
| has_history | input | Whether a preceding choice is available | binary |
| target | output | risky_choice | binary choice |

Scope: Before each choice using trial settings and only prior choices in that protocol; numeric Hidden and EV excluded.

Original source title: Dataset : Contextual influences on risk-taking in children and adults

## P100-090 · Collective rotation in pedestrian crowds

Tracked pedestrian groups form time-varying motion patterns. Explore near-future signed angular order using past motion, spatial extent and density summaries.

Package: `scenarios/P100-090/`

Task: **Predict next-window angular order**

Independent unit: Whole country/experiment-condition group with all repetitions; participants may recur across conditions and identifiers do not resolve all dependence. One teen condition keptdevelopment, no heldteen generalization.

| Variable | Role | Definition | Units |
|---|---|---|---|
| p_now | input | Current signed angular order | dimensionless current signed angular order |
| p_past | input | Mean signed angular order in the preceding two seconds | previous2integerseconds mean order |
| p_initial | input | Mean order in the disclosed initial two-second calibration | first2seconds mean order, declared pertrialcalibration |
| density | input | Tracked-person count divided by estimated circular area | tracked persons/(pi*r90²), proxy persons/m² |
| speed | input | Mean backward-secant walking speed | mean1sbackwardsecant m/s |
| radius90 | input | 90th percentile of distance from the group centroid | 90th-percentile centroiddistance metres |
| polarization_variance | input | Within-frame variance of individual signed angular order | withinframe variance of individual signedorder |
| target | output | Mean next-two-second signed angular polarization about instantaneous group centroid | dimensionless signed[-1,1] |

Scope: Every predictor uses trajectory rows at/before origin t. Integer positions use previous observed sample only, at most1second stale; current tracked count uses prefix-present IDs, never full-trial future membership. No interpolation from future. Velocities derived by backward1s differences; supplied VX/VY/Pol forbidden because smoothing provenance can include future. Target uses t+1..t+2.

Original source title: Individual locomotor bias drives counterclockwise motion in pedestrian crowds

