"""User-facing descriptions, separate from immutable scientific contracts.

Descriptions explain the released compact fields, not additional raw measurements.
Units, timing, source identity and scientific caveats still come from the contract.
"""

from __future__ import annotations

import re

# Editorial summaries of the local scenario manifests and reconstruction code.
SCENARIOS = {
    "002": (
        "Stellar brightness over time",
        "TESS satellite light curves record changes in stellar brightness. This example relates recent hourly flux summaries to the next hourly value.",
    ),
    "003": (
        "Gravitational-wave detector noise",
        "Hanford detector strain is summarized over nonoverlapping time windows. Explore relationships between recent spectral noise measurements and the next window’s strain amplitude.",
    ),
    "006": (
        "Rydberg-atom radio-frequency sensing",
        "An atomic sensor is driven under different detuning and Rabi-frequency conditions. Investigate how these controls relate to the ion-readout amplitude.",
    ),
    "012": (
        "Hafnia thin-film X-ray reflectivity",
        "X-ray reflectivity measurements characterize a hafnia-on-silicon wafer. Explore intensity as a function of scattering wavevector, position and disclosed calibration measurements.",
    ),
    "015": (
        "Household emergency-expense resilience",
        "Public household survey responses describe financial circumstances. This task estimates a reported inability to cover an unexpected expense; it does not identify a causal effect or assess an individual’s creditworthiness.",
    ),
    "017": (
        "Earthquake depth-estimation uncertainty",
        "Earthquake catalog entries include geometry and quality summaries of the seismic network. Explore their association with the catalog’s reported depth uncertainty.",
    ),
    "018": (
        "Tornado damage and event geometry",
        "Storm reports pair tornado dimensions and timing with property-damage estimates. Explore empirical damage relationships while retaining reporting and estimate uncertainty.",
    ),
    "019": (
        "Vehicle complaint volumes over time",
        "Monthly counts summarize received vehicle complaints by make and model. Explore how past complaint volumes relate to the next month’s reported count.",
    ),
    "020": (
        "Sea-surface temperature anomaly maps",
        "Satellite-derived ocean temperature anomaly maps provide spatial neighborhoods. Reconstruct a withheld pixel from nearby observations without treating interpolation as a physical mechanism.",
    ),
    "022": (
        "Perovskite memristor forming current",
        "Electrical forming sweeps measure current as voltage increases in lead-free perovskite devices. Compare voltage-response relationships across the recorded composition conditions.",
    ),
    "023": (
        "Finger-pad friction in viscous liquids",
        "Spreading experiments connect friction with liquid viscosity, motion and contact conditions. Some released descriptors are author-derived calibrations, rather than direct sensor readings.",
    ),
    "025": (
        "Battery X-ray absorption during cycling",
        "Operando iron-edge absorption spectra track a battery electrode through cycling. Investigate spectral response using disclosed reference spectra and protocol descriptors.",
    ),
    "026": (
        "Catalyst selectivity over time",
        "Silver-zeolite experiments track dimethoxymethane selectivity during reaction. Explore changes after disclosed early calibration measurements at different silver loadings.",
    ),
    "027": (
        "Vapor distribution in boiling-water flow",
        "Two-phase water-flow experiments measure local vapor void fraction. Relate radial position and operating conditions to this measured distribution.",
    ),
    "028": (
        "Parametric microwave scattering",
        "Pump-controlled microwave experiments measure an off-diagonal sideband response. Use disclosed low-pump calibrations and frequency separation to investigate the response magnitude.",
    ),
    "030": (
        "Friction with boron-nitride lubricants",
        "Lubricant tests measure friction across sliding speeds and additive concentrations. Explore the intermediate response using disclosed boundary and high-speed calibrations.",
    ),
    "031": (
        "Quantum-circuit compilation time",
        "Circuit benchmarks compare compilation tools. Investigate wall time using circuit size and an observed Qiskit pilot; this is conditional on the pilot’s computational cost.",
    ),
    "032": (
        "Short-horizon respiratory pressure",
        "Respiratory recordings contain gauge and differential pressure channels. Explore short-horizon prediction from past samples and recorded trial conditions; no clinical decision claim is implied.",
    ),
    "033": (
        "Heart rate from smartphone pulse signals",
        "Phone photoplethysmography is compared with ECG reference heart rate. Explore how spectral, autocorrelation and acquisition-quality descriptors predict the reference rate.",
    ),
    "035": (
        "Animal vocalization and recording context",
        "Ungulate vocalizations are represented by acoustic descriptors and source context labels. Explore associations with the recorded context, without inferring an animal’s emotional state.",
    ),
    "036": (
        "Plant fluorescence under stress",
        "Tomato phenotyping combines fluorescence, image-derived descriptors and treatment indicators. Explore relationships with the author-reported maximum quantum yield.",
    ),
    "039": (
        "Education, age and earnings categories",
        "Adult-skills survey data from the USA and Japan connect education and age with earnings categories. The response is a country-relative earnings category, not an absolute wage.",
    ),
    "043": (
        "Language-model training loss trajectories",
        "Gemstones training runs record validation loss as compute accumulates. Explore later loss using architecture size and disclosed early checkpoints.",
    ),
    "045": (
        "Gamma-ray burst spectral count rates",
        "Fermi GBM detector channels record a gamma-ray burst. Explore a higher-energy channel’s count rate using lower-energy channels, background and detector calibration.",
    ),
    "049": (
        "Battery voltage relaxation",
        "Lithium-graphite cell experiments record voltage after a current pulse. Investigate the relaxation curve using early voltage anchors and pulse conditions.",
    ),
    "051": (
        "Gate response in semiconductor memories",
        "Patterned metal–semiconductor memory devices are measured across gate voltage. Reconstruct drain current between three disclosed calibration anchors for each response curve.",
    ),
    "053": (
        "Torque during industrial screw driving",
        "Screw-driving cycles record torque over angle and repeated tool use. Relate early-cycle measurements and permitted past-cycle information to later thread-forming torque.",
    ),
    "054": (
        "Microfracture load and notch geometry",
        "Microscale cantilevers with bridge notches are tested to failure. Explore how reported specimen dimensions relate to the second bridge’s failure load.",
    ),
    "055": (
        "Penetration resistance of printable concrete",
        "Slag-based printable mixtures are tested by penetration. Explore normal force across mix-design descriptors, material age and the source penetration clock.",
    ),
    "062": (
        "Hydrogen permeation through steel",
        "Electrochemical permeation tests record the anodic current response of high-strength steel. Explore transient response after imposed cathodic-current steps.",
    ),
    "068": (
        "Acoustic levitation dynamics",
        "Laser Doppler vibrometer recordings track an acoustically levitated object. Explore short-horizon voltage evolution from recent, offset-corrected observations.",
    ),
    "070": (
        "Magnetic maps of laboratory fault heating",
        "Magnetic microscopy maps characterize specimens from laboratory slip experiments. Reconstruct a withheld map ordinate from nearby values; the source-native unit remains unresolved.",
    ),
    "072": (
        "Yeast competition in co-culture",
        "Wine-yeast co-cultures are followed by author-reported qPCR composition estimates. Explore later species proportions from two disclosed early measurements.",
    ),
    "074": (
        "Kinase biosensor fluorescence kinetics",
        "A biosensor experiment records fluorescence over time at different concentrations. Investigate the kinetic response using early fluorescence calibration and curvature.",
    ),
    "076": (
        "Neuronal firing and substrate conditions",
        "Stimulation experiments record evoked spike counts under substrate-stiffness and knockdown conditions. Explore conditional response after disclosed within-cell calibration.",
    ),
    "084": (
        "Cellulose biointerface force curves",
        "Atomic-force microscopy measures retraction force at a cellulose-acetate interface. Explore curve shape using calibrated position and initial force measurements.",
    ),
    "086": (
        "Fermentation potency over time",
        "Erythromycin fermentation batches include periodic potency assays. Explore a six-hour forecast using the latest measurement and its past slope.",
    ),
    "087": (
        "Cooperation in asymmetric public-goods games",
        "Repeated economic games record individual contributions and partner behavior. Explore the next contribution using only prior rounds and declared game conditions.",
    ),
    "089": (
        "Risk-taking across ages and contexts",
        "Choice experiments vary reward, probability and presentation context. Explore recorded risky choices using participant descriptors and permitted past-choice summaries.",
    ),
    "090": (
        "Collective rotation in pedestrian crowds",
        "Tracked pedestrian groups form time-varying motion patterns. Explore near-future signed angular order using past motion, spatial extent and density summaries.",
    ),
}

# Concise definitions for abbreviated or potentially misleading source columns.
FIELDS = {
    "002": {"mad6": "Median absolute deviation of the preceding six hourly flux values"},
    "003": {
        "low1": "Previous-window low-band strain amplitude",
        "high1": "Previous-window high-band strain amplitude",
        "line1": "Previous-window spectral-line amplitude",
        "mad4": "Median absolute deviation of the preceding four strain windows",
    },
    "006": {
        "detuning_MHz": "Optical detuning control",
        "rabi_MHz": "Radio-frequency Rabi-frequency control",
    },
    "012": {
        "q": "Scattering wavevector calculated from X-ray angle",
        "q0": "Mean wavevector in the disclosed calibration interval",
        "I0": "Mean intensity near the calibration angle",
        "outer": "Indicator for a noncentral wafer measurement position",
    },
    "015": {
        "income_proxy": "Income-bracket midpoint proxy",
        "shock": "Indicator for no paid or profit work in the previous month; not a job-loss measure",
        "household_size": "Number of household members",
        "age": "Respondent age",
    },
    "017": {
        "phases": "Number of seismic phases used in the origin solution",
        "stations": "Number of stations used in the origin solution",
        "rms_s": "Reported phase-residual standard error",
        "gap_deg": "Largest station azimuthal gap",
        "dmin_km": "Nearest-station angular distance converted to kilometres",
        "depth_km": "Reported earthquake depth relative to the network reference",
    },
    "020": {
        "hx": "Mean of the immediate horizontal neighbors",
        "hy": "Mean of the immediate vertical neighbors",
        "ox": "Mean of the outer horizontal neighbors",
        "oy": "Mean of the outer vertical neighbors",
        "dg": "Mean of the diagonal neighbors",
        "gx": "Absolute horizontal-neighbor contrast",
        "gy": "Absolute vertical-neighbor contrast",
        "clat": "Cosine of latitude",
    },
    "023": {
        "H": "Author-calibrated Hersey descriptor",
        "viscosity": "Author-fitted liquid viscosity at the specified shear rate",
        "hydration": "Instrument-reported skin hydration",
        "area": "Contact area",
        "speed": "Sliding speed",
        "load": "Normal contact load",
    },
    "025": {
        "pre": "Disclosed pre-edge absorption level",
        "jump": "Disclosed absorption-edge jump",
        "rL": "Normalized measured lithium-iron-phosphate reference",
        "rF": "Normalized measured iron-phosphate reference",
        "dL": "First energy derivative of the lithium-iron-phosphate reference",
        "d2L": "Second energy derivative of the lithium-iron-phosphate reference",
        "f": "Nominal protocol progress",
        "discharge": "Discharge branch indicator",
        "rest": "Rest segment indicator",
        "e": "Energy relative to the iron-edge reference",
    },
    "028": {
        "lo": "Low-pump calibration response",
        "hi": "Second disclosed calibration response",
        "noise": "Zero-pump response",
        "r": "Normalized pump increment",
        "g": "Pump-amplitude control",
        "glo": "Low calibration pump control",
        "ghi": "High calibration pump control",
        "sep": "Frequency-bin separation",
    },
    "032": {
        "di0": "Current inspiratory differential pressure",
        "de0": "Current expiratory differential pressure",
        "di20": "Inspiratory differential pressure 20 samples before the prediction origin",
        "de20": "Expiratory differential pressure 20 samples before the prediction origin",
        "trial_BH": "Source PEEP_BH trial indicator",
        "trial_FEM": "Source FEM trial indicator",
    },
    "033": {
        "fft_bpm": "Heart-rate estimate from the dominant spectral peak",
        "acf_bpm": "Heart-rate estimate from autocorrelation",
        "half_bpm": "Half-frequency candidate heart-rate estimate",
        "half_strength": "Relative spectral power near the half-frequency candidate",
        "spectral_quality": "Spectral concentration quality descriptor",
        "agreement": "Difference between candidate heart-rate estimates",
        "motion": "Recorded motion-condition descriptor",
        "ear": "Ear recording-site indicator",
    },
    "035": {
        "log_duration": "Logarithm of recording duration",
        "log_centroid": "Logarithm of spectral centroid",
        "log_peak": "Logarithm of peak frequency",
        "high_share": "High-frequency energy share",
        "entropy": "Spectral entropy",
        "flatness": "Spectral flatness",
        "envelope_cv": "Coefficient of variation of the amplitude envelope",
        "log_modulation": "Logarithm of modulation descriptor",
        "log_rms": "Logarithm of root-mean-square amplitude",
        "species_code": "Source species category encoded numerically; not an ordered biological scale",
    },
    "036": {
        "npq": "Author-reported steady-state nonphotochemical quenching",
        "rfd": "Author-reported fluorescence decline ratio",
        "ngrdi": "Normalized green-red difference image index",
        "area": "Source plant-area descriptor; physical scale requires source review",
        "tiny": "Cultivar indicator",
        "salt": "Salt-treatment indicator",
        "drought": "Drought-treatment indicator",
        "high_stress": "Second source stress-level indicator",
    },
    "039": {
        "education": "Source-derived years of formal education",
        "age": "Fixed midpoint of a published age bin",
        "japan": "Japan survey indicator",
    },
    "043": {
        "tokens_B": "Training tokens at the prediction checkpoint",
        "anchor_tokens_B": "Tokens at the disclosed anchor checkpoint",
        "early_tokens_B": "Tokens at the earlier disclosed checkpoint",
        "anchor_loss": "Validation loss at the anchor checkpoint",
        "early_loss": "Validation loss at the earlier checkpoint",
        "params_B": "Language-model parameter count",
        "width": "Embedding width",
        "depth": "Number of model layers",
    },
    "045": {
        "low": "Current count rate in lower-energy channels 2 and 3",
        "low_lag": "Lower-energy count rate in the preceding time bin",
        "background_low": "Pre-trigger background in lower-energy channels",
        "background_high": "Pre-trigger background in channel 4",
        "time_s": "Elapsed time after the burst trigger",
        "channel_low_keV": "Lower bound of the response energy channel",
        "channel_high_keV": "Upper bound of the response energy channel",
    },
    "049": {
        "t": "Elapsed time during current-free relaxation",
        "t60": "Actual time of the disclosed 60-second anchor",
        "t120": "Actual time of the disclosed 120-second anchor",
        "u60": "Voltage at the 60-second anchor",
        "u120": "Voltage at the 120-second anchor",
        "u10": "Voltage at the 10-second anchor",
        "pulse_s": "Duration of the preceding current pulse",
        "current": "Current during the preceding pulse",
    },
    "051": {
        "gate_V": "Applied gate voltage",
        "cal_minus20_uA": "Drain-current calibration at −20 V",
        "cal_zero_uA": "Drain-current calibration at 0 V",
        "cal_plus20_uA": "Drain-current calibration at +20 V",
    },
    "053": {
        "early": "Early-cycle torque summary",
        "finding": "Screw-finding torque summary",
        "gradient_proxy": "Early torque-gradient proxy",
        "roughness": "Early torque fluctuation descriptor",
        "usage": "Accumulated tool-use cycle count",
        "left": "Source left-side indicator",
        "has_history": "Whether a previous cycle is available",
        "prev_y": "Previous permitted cycle’s response torque",
        "prev_early": "Previous cycle’s early torque",
        "prev_gradient": "Previous cycle’s torque-gradient proxy",
        "first_y": "First disclosed cycle’s response torque",
        "mean_past_y": "Mean response over permitted past cycles",
        "history_gap": "Gap in cycles since the previous observation",
    },
    "054": {
        "width_um": "Cantilever specimen width",
        "thickness_um": "Cantilever specimen thickness",
        "length_um": "Cantilever specimen length",
        "notch_depth_um": "Bridge-notch depth",
        "notch_width_um": "Bridge-notch width",
    },
    "055": {
        "ratio": "Mix-design ratio encoded in the source mixture label",
        "water": "Water ratio encoded in the source mixture label",
        "age_min": "Time since mixing",
        "time_s": "Source penetration clock index; seconds are not independently established",
    },
    "062": {
        "t": "Time since the third baseline observation",
        "offset": "Mean of the first three anodic-current observations",
        "drive": "Imposed cathodic-current step",
        "high": "Known high-current condition indicator",
    },
    "068": {
        "y0": "Current LDV voltage minus the initial offset",
        "y1": "LDV voltage at the 5 ms lag minus offset",
        "y2": "LDV voltage at the 10 ms lag minus offset",
        "y3": "LDV voltage at the 15 ms lag minus offset",
        "offset": "Mean of the first 20 voltage samples",
        "t": "Stored observation timestamp",
    },
    "070": {
        "hx": "Mean of immediate horizontal neighbors",
        "hy": "Mean of immediate vertical neighbors",
        "ox": "Mean of outer horizontal neighbors",
        "oy": "Mean of outer vertical neighbors",
        "dg": "Mean of diagonal neighbors",
        "gx": "Horizontal contrast normalized by local RMS amplitude",
        "gy": "Vertical contrast normalized by local RMS amplitude",
        "lo": "Minimum neighboring ordinate",
        "hi": "Maximum neighboring ordinate",
    },
    "072": {
        "p22_pct": "Same-replicate species percentage at 22 hours",
        "p72_pct": "Same-replicate species percentage at 72 hours",
        "time_h": "Time since inoculation",
    },
    "074": {
        "concentration_uM": "Source assay concentration",
        "time_min": "Reaction time",
        "calibration_F6": "Disclosed early fluorescence anchor",
        "calibration_v6": "Disclosed early fluorescence slope",
        "calibration_curvature": "Disclosed early curvature of the fluorescence trace",
    },
    "076": {
        "current": "Applied stimulation current",
        "soft": "Soft-substrate condition indicator",
        "kd": "Knockdown condition indicator",
        "cal_mean": "Mean spike count in the disclosed calibration stimuli",
        "cal_last": "Spike count in the last disclosed calibration stimulus",
    },
    "084": {
        "x": "Normalized piezo position relative to the fixed approach-force crossing",
        "base": "Mean force in the first ten approach observations",
        "amp": "Initial retraction force minus the baseline",
        "progress": "Fraction of the retraction ramp",
    },
    "086": {
        "time_h": "Time since cultivation began",
        "current": "Last available potency assay",
        "slope6": "Potency slope over the strictly preceding six hours",
    },
    "087": {
        "round": "Game round being predicted",
        "own_previous": "Participant contribution in the previous round",
        "peer_previous": "Partner contribution in the previous round",
        "own_lag2": "Participant contribution two rounds earlier",
        "peer_lag2": "Partner contribution two rounds earlier",
        "own_history_mean": "Mean participant contribution over prior rounds",
        "peer_history_mean": "Mean partner contribution over prior rounds",
        "endowment": "Participant token endowment",
        "peer_endowment": "Partner token endowment",
        "productivity": "Participant contribution multiplier",
        "peer_productivity": "Partner contribution multiplier",
        "threshold": "Group success threshold in productivity-weighted tokens",
        "previous_success": "Whether the previous round achieved its threshold",
        "required_contribution": "Contribution requirement derived from the declared game conditions",
    },
    "089": {
        "reward": "Offered risky-option reward",
        "probability": "Offered reward probability",
        "child": "Child participant indicator",
        "age_child": "Child age; adult rows use the source sentinel",
        "multi": "Multiple-option context indicator",
        "description": "Description-based presentation indicator",
        "trial_progress": "Trial index divided by 40",
        "lag_choice": "Prior risky choice, with a first-trial prior",
        "history_mean": "Mean prior risky-choice rate, with a first-trial prior",
        "has_history": "Whether a preceding choice is available",
    },
    "090": {
        "p_now": "Current signed angular order",
        "p_past": "Mean signed angular order in the preceding two seconds",
        "p_initial": "Mean order in the disclosed initial two-second calibration",
        "density": "Tracked-person count divided by estimated circular area",
        "speed": "Mean backward-secant walking speed",
        "radius90": "90th percentile of distance from the group centroid",
        "polarization_variance": "Within-frame variance of individual signed angular order",
    },
}


OUTPUTS = {
    "002": "Next-hour stellar flux",
    "003": "Next-window strain amplitude",
    "006": "Ion-readout amplitude",
    "012": "X-ray reflectivity intensity",
    "015": "Emergency-expense inability",
    "017": "Reported depth uncertainty",
    "018": "Log property-damage estimate",
    "019": "Next-month complaint count",
    "020": "Withheld-pixel temperature anomaly",
    "022": "Forming-sweep current",
    "023": "Median friction coefficient",
    "025": "Iron-edge absorption",
    "026": "Dimethoxymethane selectivity",
    "027": "Local vapor void fraction",
    "028": "Sideband response magnitude",
    "030": "Friction coefficient",
    "031": "Mean compilation time",
    "032": "Pressure 200 ms ahead",
    "033": "ECG reference heart rate",
    "035": "Positive-context label probability",
    "036": "Maximum quantum yield",
    "039": "Upper-earnings-category membership",
    "043": "Later validation loss",
    "045": "Channel-4 count rate",
    "049": "Relaxation voltage",
    "051": "Drain current",
    "053": "Thread-forming torque",
    "054": "Second-bridge failure load",
    "055": "Penetration normal force",
    "062": "Anodic permeation current",
    "068": "LDV voltage 5 ms ahead",
    "070": "Withheld-pixel magnetic ordinate",
    "072": "Later yeast species percentage",
    "074": "Kinetic fluorescence",
    "076": "Evoked spike count",
    "084": "Retraction force",
    "086": "Potency six hours ahead",
    "087": "Next-round contribution",
    "089": "Risky choice",
    "090": "Next-window angular order",
}


def variable(task, name):
    case = task.get("parent_scenario_id", task.get("scenario_id", "")).split("-")[-1]
    units = (
        task.get("output_units", "")
        if name == task.get("output")
        else task.get("input_units", {}).get(name, "")
    )
    units = units or task.get("quantity_units", {}).get(name, "")
    supplied = task.get("variable_descriptions", {}).get(name)
    description = supplied or FIELDS.get(case, {}).get(name)
    if name == task.get("output"):
        description = supplied or task.get("output_description", task.get("title", name))
    if not description and re.fullmatch(r"(lag|median|mad)\d+", name):
        n = re.search(r"\d+", name).group()
        base = {
            "lag": "Lagged observation",
            "median": "Median of preceding observations",
            "mad": "Median absolute deviation of preceding observations",
        }[re.sub(r"\d+", "", name)]
        description = f"{base} (source window: {n}); {units}"
    if not description and case == "032" and name.startswith("p"):
        description = f"Gauge pressure {int(name[1:])} samples before the prediction origin"
    if not description:
        description = name.replace("_", " ").capitalize()
        if units:
            description += ". Recorded definition: " + units
    label = description.split(";")[0].split(". Recorded definition:")[0]
    if name == task.get("output") and case in OUTPUTS and not supplied:
        label = OUTPUTS[case]
    return {
        "key": name,
        "label": label[:120],
        "description": description,
        "units": {
            "um": "µm",
            "uA": "µA",
            "uM": "µM",
            "cmH2O": "cm H₂O",
            "degree C": "°C",
            "1": "dimensionless",
        }.get(units, units)
        or "Not documented",
        "role": "output" if name == task.get("output") else "input",
        "provenance": "Compact task contract and local preparation code; author-derived fields remain author-derived",
    }


def describe_task(task):
    case = task.get("scenario_id", "").split("-")[-1]
    title = (
        task.get("title", task["task_id"])
        if task.get("assessment_policy")
        else "Predict " + OUTPUTS.get(case, task.get("title", task["task_id"])).lower()
    )
    return {
        **task,
        "display_title": task.get("display_title", title).replace("_", " "),
        "variables": [variable(task, name) for name in [*task["inputs"], task["output"]]],
        "custom": task.get("assessment_policy") == "development_only",
    }


def describe_scenario(info, task):
    key = info.get("scenario_id", task.get("scenario_id", "")).split("-")[-1]
    title, summary = SCENARIOS.get(
        key,
        (info["title"], info.get("description", task.get("title", "User-provided measurements"))),
    )
    if info.get("local_extension"):
        title, summary = info["title"], info.get("description", summary)
    return {
        "title": title,
        "description": summary,
        "source_title": info["title"],
        "independent_unit": info.get(
            "independent_unit",
            task.get("split", {}).get("independent_unit", "User-specified groups"),
        ),
        "representation": info.get(
            "measurement_representation",
            "Native numerical measurements with explicit units and source lineage"
            if task.get("equation_templates")
            else "Numeric measurements from a local import",
        ),
    }
