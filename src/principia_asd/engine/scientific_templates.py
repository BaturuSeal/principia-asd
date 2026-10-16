"""Disclosed scientific priors for the local equation-system exploration pack.

These are competing model families, not rediscovered laws. Their parameters are fitted
afresh on training data; no reference fit or final observation is imported.
"""

from .equations import VERSION


def parameter(initial, bounds, unit, meaning):
    return dict(initial=initial, bounds=bounds, unit=unit, meaning=meaning)


def constant(value, unit, meaning, source):
    return dict(value=value, unit=unit, meaning=meaning, source=source)


def node(id, expression, unit, meaning):
    return dict(id=id, expression=expression, unit=unit, meaning=meaning)


def system(name, nodes, parameters, constants, assumptions):
    return dict(
        version=VERSION,
        name=name,
        nodes=nodes,
        parameters=parameters,
        constants=constants,
        assumptions=assumptions,
        output=nodes[-1]["id"],
    )


def resin_templates():
    constants = {
        "T_ref": constant(
            308.15,
            "K",
            "Reference temperature, 35 degrees Celsius",
            "Declared coordinate reference; not fitted",
        )
    }
    params = {
        "eta_ref": parameter(
            0.5, [0.0001, 100], "Pa*s", "Low-shear viscosity at the reference temperature"
        ),
        "activation": parameter(
            3000,
            [10, 30000],
            "K",
            "Activation energy divided by the gas constant; conditional effective parameter",
        ),
    }
    nodes = [
        node(
            "thermal_shift",
            "exp(activation * (1 / temperature - 1 / T_ref))",
            "1",
            "Arrhenius temperature shift relative to the reference temperature",
        ),
        node(
            "zero_shear_viscosity",
            "eta_ref * thermal_shift",
            "Pa*s",
            "Hypothesized low-shear viscosity at the observed temperature",
        ),
    ]
    base = system(
        "Arrhenius viscosity",
        nodes,
        params,
        constants,
        [
            "Effective activation regime over the retained temperatures",
            "No claim of a single microscopic activation barrier",
            "Newtonian reference: ignores shear-rate dependence",
        ],
    )
    cross = system(
        "Thermally shifted Cross flow",
        [
            *nodes,
            node(
                "reduced_shear",
                "shear_rate * relaxation * thermal_shift",
                "1",
                "Dimensionless shear rate relative to a temperature-shifted relaxation time",
            ),
            node(
                "shear_reduction",
                "1 / (1 + reduced_shear ** exponent)",
                "1",
                "Cross-law shear-thinning factor",
            ),
            node(
                "viscous_response",
                "zero_shear_viscosity * shear_reduction",
                "Pa*s",
                "Predicted viscosity after thermal and shear-rate contributions",
            ),
        ],
        params
        | {
            "relaxation": parameter(
                0.02, [0.000001, 100], "s", "Effective relaxation time at the reference temperature"
            ),
            "exponent": parameter(0.8, [0.05, 2], "1", "Phenomenological shear-thinning exponent"),
        },
        constants,
        [
            "Cross constitutive family with negligible infinite-shear plateau",
            "Thermorheological simplicity is a testable assumption",
            "Instrument-derived viscosity; one resin formulation, no universality claim",
        ],
    )
    return [base, cross]


def relaxation_templates():
    constants = {
        "T_ref": constant(
            313.15,
            "K",
            "Reference temperature, 40 degrees Celsius",
            "Declared coordinate reference; not fitted",
        )
    }
    common = {
        "activation": parameter(
            10000,
            [100, 60000],
            "K",
            "Effective activation temperature for time-temperature shifting",
        )
    }
    shift = node(
        "thermal_shift",
        "exp(activation * (1 / temperature - 1 / T_ref))",
        "1",
        "Temperature shift of the relaxation timescale",
    )
    templates = []
    for modes in (1, 2):
        params = dict(common)
        nodes = [shift]
        for j in range(modes):
            params[f"G{j + 1}"] = parameter(
                5e7 / modes,
                [100, 1e10],
                "Pa",
                f"Elastic strength of relaxation mode {j + 1}; labels are exchangeable",
            )
            params[f"tau{j + 1}"] = parameter(
                0.03 * 30**j, [1e-8, 1e4], "s", f"Reference relaxation time of mode {j + 1}"
            )
            nodes.extend(
                [
                    node(
                        f"z{j + 1}",
                        f"omega * tau{j + 1} * thermal_shift",
                        "1",
                        f"Angular frequency relative to relaxation mode {j + 1}",
                    ),
                    node(
                        f"storage{j + 1}",
                        f"G{j + 1} * z{j + 1} ** 2 / (1 + z{j + 1} ** 2)",
                        "Pa",
                        f"Energy-storing contribution of mode {j + 1}",
                    ),
                    node(
                        f"loss{j + 1}",
                        f"G{j + 1} * z{j + 1} / (1 + z{j + 1} ** 2)",
                        "Pa",
                        f"Dissipative contribution of mode {j + 1}",
                    ),
                ]
            )
        nodes.append(
            node(
                "modulus_response",
                "where(response_kind == 0, "
                + " + ".join(f"storage{j + 1}" for j in range(modes))
                + ", "
                + " + ".join(f"loss{j + 1}" for j in range(modes))
                + ")",
                "Pa",
                "Storage (channel 0) or loss (channel 1) modulus from the same fitted relaxation spectrum",
            )
        )
        templates.append(
            system(
                f"{'Single' if modes == 1 else 'Two'}-mode thermal relaxation",
                nodes,
                params,
                constants,
                [
                    "Linear generalized Maxwell response",
                    "Shared relaxation times and strengths across both measured response channels",
                    "Arrhenius shift is approximate across this temperature range",
                    "One polymer batch; source data are not compliance-corrected",
                ],
            )
        )
    # A distributed relaxation spectrum rather than merely adding polynomial terms.
    templates.append(
        system(
            "Fractional thermal relaxation",
            [
                shift,
                node(
                    "reduced_frequency",
                    "omega * tau * thermal_shift",
                    "1",
                    "Dimensionless frequency at the shifted relaxation timescale",
                ),
                node(
                    "spectral_power",
                    "reduced_frequency ** alpha",
                    "1",
                    "Fractional relaxation spectrum amplitude",
                ),
                node(
                    "phase_cosine",
                    "cos(alpha * pi / 2)",
                    "1",
                    "Cosine of the fractional constitutive phase",
                ),
                node(
                    "phase_sine",
                    "sin(alpha * pi / 2)",
                    "1",
                    "Sine of the fractional constitutive phase",
                ),
                node(
                    "spectral_denominator",
                    "1 + 2 * spectral_power * phase_cosine + spectral_power ** 2",
                    "1",
                    "Squared complex denominator of the fractional Maxwell response",
                ),
                node(
                    "storage_modulus",
                    "G * spectral_power * (phase_cosine + spectral_power) / spectral_denominator",
                    "Pa",
                    "Elastic storage response of the fractional spectrum",
                ),
                node(
                    "loss_modulus",
                    "G * spectral_power * phase_sine / spectral_denominator",
                    "Pa",
                    "Dissipative response of the same fractional spectrum",
                ),
                node(
                    "modulus_response",
                    "where(response_kind == 0, storage_modulus, loss_modulus)",
                    "Pa",
                    "Jointly predicted storage or loss channel",
                ),
            ],
            common
            | {
                "G": parameter(1e8, [100, 1e10], "Pa", "High-frequency elastic strength"),
                "tau": parameter(0.1, [1e-8, 1e4], "s", "Reference relaxation timescale"),
                "alpha": parameter(
                    0.65,
                    [0.05, 1],
                    "1",
                    "Fractional spectral exponent; one recovers a single Maxwell mode at unity",
                ),
            },
            constants
            | {"pi": constant(3.141592653589793, "1", "Circle constant", "Mathematical constant")},
            [
                "Fractional Maxwell family with a distributed relaxation spectrum",
                "Same parameters bind storage and loss; neither channel is an input proxy for the other",
                "Fractional order is phenomenological, not a directly measured molecular quantity",
                "One batch and no compliance correction; independent mechanism validation remains absent",
            ],
        )
    )
    return templates


def atmosphere_templates():
    constants = {
        "sigma": constant(
            5.670374419e-8, "W/m2/K4", "Stefan-Boltzmann constant", "CODATA SI radiation constant"
        ),
        "T_ref": constant(
            300, "K", "Temperature normalization", "Declared fixed coordinate reference"
        ),
        "e_ref": constant(
            1000, "Pa", "Vapor-pressure normalization", "Declared fixed coordinate reference"
        ),
    }
    blackbody = node(
        "blackbody_irradiance",
        "sigma * temperature ** 4",
        "W/m2",
        "Blackbody longwave irradiance at the measured near-surface temperature",
    )
    gray = system(
        "Gray-atmosphere emission",
        [
            blackbody,
            node(
                "longwave_response",
                "emissivity * blackbody_irradiance",
                "W/m2",
                "Atmospheric longwave irradiance under an effective gray emissivity",
            ),
        ],
        {
            "emissivity": parameter(
                0.8, [0.05, 1], "1", "Effective sky emissivity, conditional on sampled conditions"
            )
        },
        {"sigma": constants["sigma"]},
        [
            "Near-surface temperature proxies the radiating atmosphere",
            "Effective emissivity is constant across all retained conditions; clouds are unresolved",
        ],
    )
    vapor = system(
        "Humidity-modulated sky emission",
        [
            blackbody,
            node(
                "reduced_humidity",
                "(vapor_pressure / e_ref) / (temperature / T_ref)",
                "1",
                "Normalized vapor-pressure / absolute-temperature ratio",
            ),
            node(
                "sky_emissivity",
                "minimum(1, amplitude * reduced_humidity ** exponent)",
                "1",
                "Bounded empirical atmospheric emissivity",
            ),
            node(
                "longwave_response",
                "sky_emissivity * blackbody_irradiance",
                "W/m2",
                "Longwave irradiance from the emissivity-temperature decomposition",
            ),
        ],
        {
            "amplitude": parameter(
                0.8, [0.1, 1], "1", "Effective emissivity scale at the normalization point"
            ),
            "exponent": parameter(
                0.14, [0.01, 0.6], "1", "Humidity response exponent in a Brutsaert-inspired family"
            ),
        },
        constants,
        [
            "Brutsaert-inspired clear-sky family evaluated on all retained weather conditions",
            "Humidity is derived from simultaneous temperature and relative humidity using the documented saturation-vapor formula",
            "Clouds and vertical profiles are omitted; transfer failure is retained",
            "Sourced constitutive prior, not an independently discovered radiation law",
        ],
    )
    return [gray, vapor]
