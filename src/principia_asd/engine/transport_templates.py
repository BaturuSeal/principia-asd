"""Explicit competing constitutive priors; never claims of newly discovered laws.

All coefficients are refitted on train. Calibration anchors are disclosed inputs.
Dimensionless ratios keep empirical exponents physically well-defined.
"""

from .scientific_templates import constant as c
from .scientific_templates import node as n
from .scientific_templates import parameter as p
from .scientific_templates import system as s


def cure_templates():
    constants = {
        "T_ref": c(
            423.15, "K", "150 Celsius reference temperature", "Declared reference coordinate"
        )
    }
    params = {
        "k1": p(0.0002, [1e-8, 0.1], "s^-1", "Non-autocatalytic reference rate"),
        "E1": p(8000, [100, 30000], "K", "Activation energy divided by gas constant"),
        "order": p(1.5, [0.1, 5], "1", "Effective depletion order"),
    }
    nodes = [
        n(
            "thermal_rate",
            "k1 * exp(E1 * (1 / T_ref - 1 / temperature))",
            "s^-1",
            "Thermally activated baseline rate",
        ),
        n(
            "remaining_fraction",
            "maximum(0, 1 - conversion)",
            "1",
            "Unconverted fraction in the measured calorimetric coordinate",
        ),
        n(
            "depletion",
            "remaining_fraction ** order",
            "1",
            "Reaction slowdown as unconverted material is depleted",
        ),
        n("conversion_rate", "thermal_rate * depletion", "s^-1", "Predicted conversion rate"),
    ]
    assumptions = [
        "Arrhenius effective kinetics over the measured thermal scans",
        "Conversion and rate are related calorimetric reductions, not independent response channels",
        "Known kinetic families; microscopic reaction mechanism is not identified",
    ]
    base = s("Arrhenius depletion kinetics", nodes, params, constants, assumptions)
    params = params | {
        "k2": p(0.002, [1e-8, 1], "s^-1", "Autocatalytic reference rate"),
        "E2": p(9000, [100, 30000], "K", "Autocatalytic activation temperature"),
        "autocat_order": p(1, [0.1, 4], "1", "Effective autocatalytic order"),
    }
    nodes = [
        *nodes[:-1],
        n(
            "autocatalytic_rate",
            "k2 * exp(E2 * (1 / T_ref - 1 / temperature)) * maximum(0, conversion) ** autocat_order",
            "s^-1",
            "Conversion-assisted reaction pathway",
        ),
        n(
            "conversion_rate",
            "(thermal_rate + autocatalytic_rate) * depletion",
            "s^-1",
            "Combined baseline and autocatalytic pathways",
        ),
    ]
    kamal = s(
        "Parallel autocatalytic cure pathways",
        nodes,
        params,
        constants,
        assumptions + ["Kamal-Sourour family with shared coefficients across heating rates"],
    )
    return [base, kamal]


def membrane_templates():
    constants = {
        "T_ref": c(
            298.15, "K", "25 Celsius reference temperature", "Declared reference coordinate"
        ),
        "p_ref": c(100000, "Pa", "One bar pressure scale", "Exact SI conversion of one bar"),
    }
    nodes = [
        n(
            "pressure_drive",
            "(pressure_feed - pressure_permeate) / p_ref",
            "1",
            "Dimensionless pressure difference across the membrane",
        ),
        n(
            "knudsen_factor",
            "sqrt(T_ref / temperature)",
            "1",
            "Knudsen molar-flux temperature scaling",
        ),
        n(
            "knudsen_flux",
            "K_ref * knudsen_factor * pressure_drive",
            "mol/m2/s",
            "Molecule-wall transport contribution",
        ),
    ]
    params = {
        "K_ref": p(
            0.5,
            [1e-6, 100],
            "mol/m2/s",
            "Reference Knudsen flux scale per one-bar driving difference",
        )
    }
    assumptions = [
        "Single S-HT membrane, pure nitrogen; no independent membrane replication",
        "Known transport families, not direct pore-size identification",
    ]
    base = s("Knudsen pore transport", nodes, params, constants, assumptions)
    mixed = s(
        "Knudsen and viscous pore transport",
        [
            *nodes,
            n(
                "mean_pressure",
                "(pressure_feed + pressure_permeate) / (2 * p_ref)",
                "1",
                "Mean pressure relative to one bar",
            ),
            n(
                "viscosity_factor",
                "(T_ref / temperature) ** (1 + viscosity_exponent)",
                "1",
                "Inverse viscosity and ideal-gas density correction",
            ),
            n(
                "viscous_flux",
                "V_ref * mean_pressure * pressure_drive * viscosity_factor",
                "mol/m2/s",
                "Pressure-driven viscous transport contribution",
            ),
            n(
                "total_flux",
                "knudsen_flux + viscous_flux",
                "mol/m2/s",
                "Parallel transport through the effective porous structure",
            ),
        ],
        params
        | {
            "V_ref": p(0.2, [1e-6, 100], "mol/m2/s", "Reference viscous flux scale"),
            "viscosity_exponent": p(
                0.7, [0.1, 1.5], "1", "Approximate nitrogen viscosity temperature exponent"
            ),
        },
        constants,
        assumptions
        + [
            "Additive effective Knudsen and viscous contributions",
            "A viscosity power law approximates the finite measured temperature range",
        ],
    )
    return [base, mixed]


def thermal_templates():
    params = {
        "capacity": p(
            3000,
            [10, 1e6],
            "J/K",
            "Effective lubricant thermal capacity under the measured torque-power convention",
        ),
        "conductance_housing": p(
            1, [1e-5, 1000], "W/K", "Effective lubricant-to-housing thermal conductance"
        ),
        "conductance_environment": p(
            0.1, [1e-5, 1000], "W/K", "Effective direct environmental heat-loss conductance"
        ),
    }
    nodes = [
        n(
            "friction_power",
            "abs(torque * speed)",
            "W",
            "Instantaneous frictional mechanical power available as heat",
        ),
        n(
            "housing_loss",
            "conductance_housing * (lubricant_temperature - housing_temperature)",
            "W",
            "Heat flow to the measured housing",
        ),
        n(
            "environment_loss",
            "conductance_environment * (lubricant_temperature - environment_temperature)",
            "W",
            "Direct effective heat flow to the measured environment",
        ),
        n(
            "net_power",
            "friction_power - housing_loss - environment_loss",
            "W",
            "Net instantaneous power into the lubricant thermal store",
        ),
        n(
            "total_conductance",
            "conductance_housing + conductance_environment",
            "W/K",
            "Combined effective heat-loss conductance",
        ),
        n(
            "relaxation_fraction",
            "1 - exp(-total_conductance * horizon / capacity)",
            "1",
            "Exact relaxation fraction for a locally constant thermal boundary",
        ),
        n(
            "temperature_increment",
            "net_power / total_conductance * relaxation_fraction",
            "K",
            "Predicted lubricant temperature change over the next minute",
        ),
    ]
    assumptions = [
        "Lumped thermal balance with measured instantaneous torque and speed",
        "Housing, environment and friction power are held locally constant over 60 seconds; later controls are never supplied",
        "Capacity and conductances are effective quantities; one joint, no independent-machine validation",
    ]
    base = s("Friction-heated thermal resistance network", nodes, params, {}, assumptions)
    # An explicit nested alternative tests speed-dependent lubricant mixing.
    variable_nodes = [
        n(
            "mixing_multiplier",
            "1 + mixing * abs(speed) / speed_ref",
            "1",
            "Hypothesized speed-dependent convective mixing enhancement",
        ),
        n(
            "housing_conductance",
            "conductance_housing * mixing_multiplier",
            "W/K",
            "Speed-dependent lubricant-to-housing conductance",
        ),
    ]
    from copy import deepcopy

    extended = deepcopy(nodes)
    for x in extended:
        x["expression"] = x["expression"].replace("conductance_housing", "housing_conductance")
    mixed = s(
        "Thermal network with speed-dependent mixing",
        variable_nodes + extended,
        params | {"mixing": p(0.3, [0.001, 20], "1", "Speed-related conductance enhancement")},
        {
            "speed_ref": c(
                1, "rad/s", "One radian per second speed reference", "Declared coordinate scale"
            )
        },
        assumptions + ["Convection proxy, not direct measurement of lubricant circulation"],
    )
    return [base, mixed]


def soil_templates():
    constants = {
        "T_ref": c(
            283.15, "K", "10 Celsius reference soil temperature", "Declared reference coordinate"
        ),
        "temperature_step": c(10, "K", "Ten-kelvin increment for Q10", "Definition of Q10"),
    }
    params = {
        "respiration_ref": p(1e-7, [1e-11, 1e-4], "kg/m2/s", "Reference ecosystem CO2 mass flux"),
        "q10": p(2, [1.001, 8], "1", "Effective flux multiplier for ten kelvin warming"),
        "root_fraction": p(
            0.4,
            [0, 0.95],
            "1",
            "Conditional reduction associated with root exclusion; not a causal attribution",
        ),
    }
    nodes = [
        n(
            "thermal_activity",
            "q10 ** ((temperature - T_ref) / temperature_step)",
            "1",
            "Temperature-dependent biological activity multiplier",
        ),
        n(
            "root_factor",
            "1 - root_fraction * root_exclusion",
            "1",
            "Conditional root-exclusion multiplier",
        ),
        n(
            "respiration",
            "respiration_ref * thermal_activity * root_factor",
            "kg/m2/s",
            "Predicted CO2 mass flux without a moisture limitation",
        ),
    ]
    assumptions = [
        "Q10 is a finite-range ecosystem response, not a universal activation law",
        "Site-held-out transfer with unmodelled soil, management and instrument differences",
        "Source flux is an author-derived chamber measurement; concentration-fit slope and intercept are prohibited predictors",
    ]
    base = s("Temperature and root-associated respiration", nodes, params, constants, assumptions)
    moist = s(
        "Moisture-limited soil respiration",
        [
            *nodes[:-1],
            n(
                "water_availability",
                "water_fraction / (water_half + water_fraction)",
                "1",
                "Saturating water-availability factor",
            ),
            n(
                "oxygen_access",
                "exp(-wet_inhibition * water_fraction ** 2)",
                "1",
                "Phenomenological suppression under high water content",
            ),
            n(
                "respiration",
                "respiration_ref * thermal_activity * root_factor * water_availability * oxygen_access",
                "kg/m2/s",
                "Combined thermal, water and oxygen-access response",
            ),
        ],
        params
        | {
            "water_half": p(0.1, [0.001, 1], "1", "Half-saturation volumetric water fraction"),
            "wet_inhibition": p(2, [0.001, 30], "1", "High-moisture inhibition strength"),
        },
        constants,
        assumptions
        + ["Water content is not pore saturation; oxygen access is an unmeasured hypothesis"],
    )
    return [base, moist]


def boiling_templates():
    nodes = [
        n(
            "gas_flux",
            "quality * mass_flux / vapor_density",
            "m/s",
            "Superficial vapor volumetric velocity from mass quality",
        ),
        n(
            "liquid_flux",
            "(1 - quality) * mass_flux / liquid_density",
            "m/s",
            "Superficial liquid volumetric velocity",
        ),
        n("mixture_flux", "gas_flux + liquid_flux", "m/s", "Total superficial mixture velocity"),
        n(
            "bulk_void",
            "gas_flux / (distribution * mixture_flux + drift_velocity)",
            "1",
            "Drift-flux effective vapor fraction before radial redistribution",
        ),
        n(
            "radial_odds",
            "exp(radial_shape * (1 - radial_fraction ** 2))",
            "1",
            "Relative radial redistribution of vapor odds",
        ),
        n(
            "void_fraction",
            "bulk_void * radial_odds / (1 - bulk_void + bulk_void * radial_odds)",
            "1",
            "Bounded local vapor void fraction",
        ),
    ]
    params = {
        "distribution": p(1.2, [1, 3], "1", "Effective phase-distribution coefficient"),
        "drift_velocity": p(0.2, [1e-6, 10], "m/s", "Effective relative vapor drift velocity"),
        "radial_shape": p(0.2, [-4, 4], "1", "Signed radial redistribution strength"),
    }
    assumptions = [
        "Drift-flux family; local radial profile is a separate phenomenological correction",
        "Source radial coordinate is normalized by the maximum sampled coordinate, not a certified tube radius",
        "Densities are fixed pressure-derived IAPWS approximations; no target-fitted fluid property",
        "Whole source runs held out; same apparatus and some shared acquisition days",
    ]
    base = s("Vapor drift with radial redistribution", nodes, params, {}, assumptions)
    return [
        base,
        s(
            "Homogeneous mixture with radial redistribution",
            [
                *nodes[:3],
                n(
                    "bulk_void",
                    "gas_flux / mixture_flux",
                    "1",
                    "Homogeneous no-slip vapor fraction",
                ),
                *nodes[4:],
            ],
            {"radial_shape": params["radial_shape"]},
            {},
            assumptions + ["No phase slip; a deliberately simpler competing explanation"],
        ),
    ]


def training_templates():
    params = {"decay": p(0.4, [0.01, 3], "1", "Shared asymptotic training-loss decay exponent")}
    nodes = [
        n(
            "anchor_ratio",
            "(early_tokens / anchor_tokens) ** decay",
            "1",
            "Power-law decay between disclosed early checkpoints",
        ),
        n(
            "loss_floor",
            "(anchor_loss - early_loss * anchor_ratio) / (1 - anchor_ratio)",
            "1",
            "Conditional asymptotic loss inferred algebraically from the two disclosed anchors",
        ),
        n(
            "remaining_excess",
            "(anchor_loss - loss_floor) * (anchor_tokens / tokens) ** decay",
            "1",
            "Unlearned loss above the conditional floor at later token counts",
        ),
        n(
            "predicted_loss",
            "loss_floor + remaining_excess",
            "1",
            "Later validation loss under the shared scaling exponent",
        ),
    ]
    assumptions = [
        "Known power-law scaling family with observed early calibration",
        "An algebraically inferred floor is not a measured entropy or an independent learned parameter",
        "Whole architectures held out; common training corpus, no external-model replication",
    ]
    base = s("Calibrated asymptotic learning dynamics", nodes, params, {}, assumptions)
    from copy import deepcopy

    extended = deepcopy(nodes)
    for x in extended:
        x["expression"] = x["expression"].replace("decay", "architecture_decay")
    arch = s(
        "Capacity-modulated learning dynamics",
        [
            n(
                "architecture_decay",
                "decay * (model_size / size_ref) ** capacity_exponent",
                "1",
                "Hypothesized architecture-size modulation of the learning rate exponent",
            ),
            *extended,
        ],
        params
        | {
            "capacity_exponent": p(
                0, [-0.3, 0.3], "1", "Weak size dependence of the loss decay exponent"
            )
        },
        {
            "size_ref": c(
                1,
                "1",
                "One billion parameters in the documented model-size coordinate",
                "Declared coordinate scale",
            )
        },
        assumptions,
    )
    return [base, arch]


def battery_templates():
    nodes = [
        n(
            "relaxation_time",
            "time_multiplier * pulse_duration",
            "s",
            "Effective relaxation timescale tied to the preceding pulse duration",
        ),
        n(
            "anchor_decay",
            "exp(-(anchor_time_late - anchor_time_early) / relaxation_time)",
            "1",
            "Decay between the two disclosed voltage anchors",
        ),
        n(
            "equilibrium_voltage",
            "(voltage_late - anchor_decay * voltage_early) / (1 - anchor_decay)",
            "V",
            "Algebraic effective equilibrium voltage from the early rest anchors",
        ),
        n(
            "residual_voltage",
            "(voltage_late - equilibrium_voltage) * exp(-(elapsed - anchor_time_late) / relaxation_time)",
            "V",
            "Remaining polarization after the last disclosed anchor",
        ),
        n(
            "relaxed_voltage",
            "equilibrium_voltage + residual_voltage",
            "V",
            "Predicted later current-free voltage",
        ),
    ]
    assumptions = [
        "Known relaxation families conditional on 60/120-second observations",
        "Single half-cell and chronological held-out rest blocks; no independent-cell validation",
        "No diffusion coefficient or unique electrochemical mechanism is identified",
    ]
    exp = s(
        "Calibrated polarization relaxation",
        nodes,
        {"time_multiplier": p(1, [0.01, 100], "1", "Relaxation-to-pulse duration ratio")},
        {},
        assumptions,
    )
    # Square-root response of a finite-duration pulse under semi-infinite diffusion.
    nodes = [
        n(
            "diffusion_now",
            "sqrt((elapsed + pulse_duration) / time_ref) - sqrt(elapsed / time_ref)",
            "1",
            "Finite-pulse diffusion relaxation shape at the prediction horizon",
        ),
        n(
            "diffusion_early",
            "sqrt((anchor_time_early + pulse_duration) / time_ref) - sqrt(anchor_time_early / time_ref)",
            "1",
            "Diffusion shape at the earlier calibration time",
        ),
        n(
            "diffusion_late",
            "sqrt((anchor_time_late + pulse_duration) / time_ref) - sqrt(anchor_time_late / time_ref)",
            "1",
            "Diffusion shape at the later calibration time",
        ),
        n(
            "polarization_scale",
            "(voltage_early - voltage_late) / (diffusion_early - diffusion_late)",
            "V",
            "Polarization amplitude algebraically calibrated from disclosed early observations",
        ),
        n(
            "relaxed_voltage",
            "voltage_late + transport_scale * polarization_scale * (diffusion_now - diffusion_late)",
            "V",
            "Later voltage under finite-pulse diffusion decay",
        ),
    ]
    diffusion = s(
        "Finite-pulse diffusion relaxation",
        nodes,
        {
            "transport_scale": p(
                1, [0.01, 10], "1", "Shared correction to the ideal finite-pulse response"
            )
        },
        {"time_ref": c(1, "s", "One-second coordinate scale", "Declared coordinate scale")},
        assumptions
        + [
            "Semi-infinite diffusion approximation; finite-particle and multiple-process deviations retained"
        ],
    )
    return [exp, diffusion]


def kinase_templates():
    constants = {
        "anchor_time": c(
            360, "s", "Six-minute disclosed calibration endpoint", "Native assay sampling protocol"
        )
    }
    params = {"rate": p(0.0005, [1e-6, 0.05], "s^-1", "Effective signal-saturation rate")}
    nodes = [
        n(
            "elapsed_after_calibration",
            "elapsed - anchor_time",
            "s",
            "Time after the last disclosed fluorescence anchor",
        ),
        n(
            "remaining_response",
            "exp(-rate * elapsed_after_calibration)",
            "1",
            "Remaining fraction of an effective first-order response",
        ),
        n(
            "integrated_signal",
            "initial_slope / rate * (1 - remaining_response)",
            "a.u.",
            "Integrated incremental fluorescence from the observed initial slope",
        ),
        n(
            "fluorescence",
            "initial_signal + integrated_signal",
            "a.u.",
            "Later instrument fluorescence after calibration",
        ),
    ]
    assumptions = [
        "Effective saturation kinetics, not identified catalytic reaction steps",
        "Initial signal and slope use only 3, 4.5 and 6 minute observations",
        "Whole biosensor-dose curves held out, with no biological replicate identities",
        "Fluorescence is uncalibrated instrument response and cannot be interpreted as molar product",
    ]
    base = s("Calibrated first-order assay response", nodes, params, constants, assumptions)
    from copy import deepcopy

    extended = deepcopy(nodes)
    for x in extended:
        x["expression"] = x["expression"].replace("rate", "dose_rate")
    # Avoid replacing substrings of node identifiers (integrated_signal) above.
    extended[2]["id"] = "integrated_signal"
    extended[3]["expression"] = "initial_signal + integrated_signal"
    dose = s(
        "Dose-modulated assay saturation",
        [
            n(
                "dose_rate",
                "rate / (1 + concentration / half_concentration)",
                "s^-1",
                "Hypothesized substrate-dose modulation of the effective saturation rate",
            ),
            *extended,
        ],
        params
        | {
            "half_concentration": p(
                0.005,
                [1e-6, 1],
                "mol/m3",
                "Effective concentration scale, not a validated Michaelis constant",
            )
        },
        constants,
        assumptions,
    )
    return [base, dose]


TEMPLATES = {
    "013": cure_templates,
    "027": boiling_templates,
    "043": training_templates,
    "049": battery_templates,
    "061": membrane_templates,
    "069": thermal_templates,
    "074": kinase_templates,
    "082": soil_templates,
}
