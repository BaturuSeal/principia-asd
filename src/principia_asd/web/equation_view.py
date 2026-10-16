"""Paper-style equations and semantic quantities from the executable DAG itself."""

import ast
import re

from ..catalog.presentation import variable
from ..engine.equations import validate


def equation_view(card, task):
    system = card["equation_system"]
    validate(system, task)
    conventional = {
        "temperature": "T",
        "omega": r"\omega",
        "shear_rate": r"\dot{\gamma}",
        "vapor_pressure": "e",
        "response_kind": "c",
        "thermal_shift": "a_T",
        "storage_modulus": "G'",
        "loss_modulus": "G''",
        "pi": r"\pi",
        "sigma": r"\sigma",
        "T_ref": "T_0",
        "e_ref": "e_0",
        "alpha": r"\alpha",
        "activation": r"T_{\mathrm a}",
        "emissivity": r"\varepsilon",
        "eta_ref": r"\eta_{\mathrm{ref}}",
        "exponent": "n",
        "relaxation": r"\tau_{\mathrm{ref}}",
        "yield_stress_ref": r"\sigma_{\mathrm y}",
        "blackbody_irradiance": r"E_{\mathrm{bb}}",
        "zero_shear_viscosity": r"\eta_0",
        "reduced_shear": r"\dot{\gamma}_{\mathrm r}",
        "carreau_factor": r"f_{\mathrm C}",
        "cross_factor": r"f_{\mathrm C}",
        "shear_reduction": r"f_{\mathrm C}",
        "yield_contribution": r"\eta_{\mathrm y}",
        "storage_total": "G'",
        "loss_total": "G''",
        "conversion": r"\alpha",
        "heating_rate": r"\dot T",
        "E1": r"T_{\mathrm a,1}",
        "E2": r"T_{\mathrm a,2}",
        "k1": "k_1",
        "k2": "k_2",
        "order": "n",
        "autocat_order": "m",
        "thermal_rate": r"k_{\mathrm d}",
        "autocatalytic_rate": r"k_{\mathrm a}",
        "remaining_fraction": "u",
        "depletion": "d",
        "mass_flux": "G",
        "quality": "x",
        "vapor_density": r"\rho_{\mathrm g}",
        "liquid_density": r"\rho_{\mathrm l}",
        "radial_fraction": "r_*",
        "distribution": "C_0",
        "drift_velocity": r"v_{\mathrm d}",
        "radial_shape": r"\beta_r",
        "gas_flux": r"j_{\mathrm g}",
        "liquid_flux": r"j_{\mathrm l}",
        "mixture_flux": "j",
        "bulk_void": r"\alpha_{\mathrm b}",
        "radial_odds": "w_r",
        "tokens": "N",
        "early_tokens": "N_1",
        "anchor_tokens": "N_2",
        "early_loss": "L_1",
        "anchor_loss": "L_2",
        "model_size": "M",
        "size_ref": "M_0",
        "decay": r"\gamma",
        "capacity_exponent": r"\beta_M",
        "anchor_ratio": "r_N",
        "architecture_decay": r"\gamma_M",
        "loss_floor": r"L_\infty",
        "remaining_excess": r"\Delta L",
        "elapsed": "t",
        "anchor_time_early": "t_1",
        "anchor_time_late": "t_2",
        "voltage_early": "V_1",
        "voltage_late": "V_2",
        "pulse_duration": "t_p",
        "time_ref": "t_0",
        "time_multiplier": r"\lambda_t",
        "transport_scale": r"\lambda_D",
        "relaxation_time": r"\tau",
        "anchor_decay": "r_V",
        "equilibrium_voltage": r"V_\infty",
        "polarization_scale": "A_V",
        "residual_voltage": r"\Delta V",
        "diffusion_early": "f_1",
        "diffusion_late": "f_2",
        "diffusion_now": "f_t",
        "pressure_feed": "p_f",
        "pressure_permeate": "p_p",
        "p_ref": "p_0",
        "K_ref": "K_0",
        "V_ref": "B_0",
        "viscosity_exponent": r"n_\mu",
        "mean_pressure": r"\bar p",
        "pressure_drive": r"\Delta p_*",
        "knudsen_factor": "f_K",
        "knudsen_flux": "J_K",
        "viscosity_factor": r"f_\mu",
        "viscous_flux": "J_V",
        "lubricant_temperature": "T_L",
        "housing_temperature": "T_H",
        "environment_temperature": "T_E",
        "torque": r"\tau_f",
        "speed": r"\omega",
        "speed_ref": r"\omega_0",
        "horizon": r"\Delta t",
        "capacity": "C_L",
        "conductance_housing": "H_0",
        "conductance_environment": "H_E",
        "mixing": r"\beta_\omega",
        "mixing_multiplier": r"f_\omega",
        "housing_conductance": "H_L",
        "friction_power": "P_f",
        "housing_loss": "Q_H",
        "environment_loss": "Q_E",
        "net_power": r"P_{\mathrm{net}}",
        "total_conductance": r"H_\Sigma",
        "relaxation_fraction": "f_t",
        "concentration": "c",
        "half_concentration": "K_c",
        "initial_signal": "F_0",
        "initial_slope": "v_0",
        "time": "t",
        "anchor_time": "t_0",
        "rate": "k",
        "dose_rate": "k_c",
        "elapsed_after_calibration": r"\Delta t",
        "remaining_response": "r_F",
        "integrated_signal": r"\Delta F",
        "water_fraction": r"\theta_w",
        "root_exclusion": "I_r",
        "q10": "Q_{10}",
        "respiration_ref": "R_0",
        "root_fraction": "f_r",
        "water_half": "K_w",
        "wet_inhibition": r"\beta_w",
        "temperature_step": r"\Delta T_0",
        "thermal_activity": "f_T",
        "root_factor": "f_R",
        "water_availability": "f_W",
        "oxygen_access": "f_O",
    }
    indexed = {
        "G": "G",
        "tau": r"\tau",
        "alpha": r"\alpha",
        "z": "z",
        "reduced_frequency": "z",
        "spectral_power": "r",
        "phase_cosine": "C",
        "phase_sine": "S",
        "spectral_denominator": "D",
        "storage": "G'",
        "loss": "G''",
    }
    used = set()

    def symbol(key, fallback):
        candidate = conventional.get(key)
        if candidate is None:
            match = re.fullmatch(r"([A-Za-z_]+?)([0-9]*)", key)
            if match and match[1] in indexed:
                candidate = indexed[match[1]]
                if match[2]:
                    candidate += "_{" + match[2] + "}"
        candidate = candidate or fallback
        if candidate in used:
            candidate = fallback
        used.add(candidate)
        return candidate

    symbols = {k: symbol(k, f"x_{{{i + 1}}}") for i, k in enumerate(task["inputs"])}
    params = []
    for i, (k, spec) in enumerate(system["parameters"].items()):
        symbols[k] = symbol(k, f"\\theta_{{{i + 1}}}")
        params.append(
            dict(
                symbol=symbols[k],
                key=k,
                value=card["parameters"][k],
                description=spec["meaning"] + " · " + spec["unit"],
                unit=spec["unit"],
                kind="fitted",
            )
        )
    for i, (k, spec) in enumerate(system.get("constants", {}).items()):
        symbols[k] = symbol(k, f"c_{{{i + 1}}}")
        params.append(
            dict(
                symbol=symbols[k],
                key=k,
                value=spec["value"],
                description=spec["meaning"] + " · " + spec["unit"] + "; fixed: " + spec["source"],
                unit=spec["unit"],
                kind="fixed",
            )
        )
    for i, n in enumerate(system["nodes"]):
        symbols[n["id"]] = (
            r"\hat{y}" if n["id"] == system["output"] else symbol(n["id"], f"q_{{{i + 1}}}")
        )

    def render(n):
        if isinstance(n, ast.Name):
            return symbols[n.id]
        if isinstance(n, ast.Constant):
            return str(n.value)
        if isinstance(n, ast.UnaryOp):
            return ("-" if isinstance(n.op, ast.USub) else "+") + "{" + render(n.operand) + "}"
        if isinstance(n, ast.BinOp):
            a, b = render(n.left), render(n.right)
            if isinstance(n.op, ast.Div):
                return r"\frac{" + a + "}{" + b + "}"
            if isinstance(n.op, ast.Pow):
                return "{" + a + "}^{" + b + "}"
            op = {ast.Mult: r"\,", ast.Add: "+", ast.Sub: "-"}[type(n.op)]
            return r"\left(" + a + op + b + r"\right)"
        if isinstance(n, ast.Compare):
            op = {
                ast.Eq: "=",
                ast.NotEq: r"\ne",
                ast.Lt: "<",
                ast.LtE: r"\le",
                ast.Gt: ">",
                ast.GtE: r"\ge",
            }[type(n.ops[0])]
            return render(n.left) + op + render(n.comparators[0])
        if isinstance(n, ast.Call):
            a = [render(x) for x in n.args]
            f = n.func.id
            if f == "where":
                return (
                    r"\begin{cases}"
                    + a[1]
                    + " & "
                    + a[0]
                    + r"\\"
                    + a[2]
                    + r" & \text{otherwise}\end{cases}"
                )
            if f == "sqrt":
                return r"\sqrt{" + a[0] + "}"
            if f == "abs":
                return r"\left|" + a[0] + r"\right|"
            if f == "log1p":
                return r"\log\left(1+" + a[0] + r"\right)"
            return (
                "\\"
                + {"minimum": "min", "maximum": "max"}.get(f, f)
                + r"\left("
                + ",".join(a)
                + r"\right)"
            )
        raise ValueError("Unsupported equation display")

    equations = []
    for n in system["nodes"]:
        dependencies = sorted(
            {
                x.id
                for x in ast.walk(ast.parse(n["expression"], mode="eval"))
                if isinstance(x, ast.Name) and x.id in symbols
            }
        )
        equations.append(
            dict(
                id=n["id"],
                symbol=symbols[n["id"]],
                latex=symbols[n["id"]]
                + " = "
                + render(ast.parse(n["expression"], mode="eval").body),
                meaning=n["meaning"],
                unit=n["unit"],
                dependencies=dependencies,
            )
        )
    return {
        "regions": [],
        "expanded_latex": None,
        "name": system["name"],
        "family_name": system["name"],
        "latex": r"\begin{aligned}"
        + r"\\[0.4em]".join(e["latex"].replace(" = ", " &= ", 1) for e in equations)
        + r"\end{aligned}",
        "equations": equations,
        "assumptions": system["assumptions"],
        "parameters": params,
        "variables": [{"symbol": symbols[k], **variable(task, k)} for k in task["inputs"]]
        + [{"symbol": r"\hat{y}", **variable(task, task["output"])}],
        "interpretation": "The response is computed through the connected quantities below. Each intermediate is executed numerically, and the same fitted parameter value is shared wherever its symbol reappears.",
        "interpretation_scope": "A unit-consistent constitutive hypothesis. Dimensional consistency and predictive performance alone do not verify its mechanism or uniqueness.",
        "formula_scope": "The equation graph preserves every operation and shared parameter. Fixed physical constants are distinguished from fitted coefficients.",
        "source_identity": card.get("rule_id", ""),
        "identifiability": card.get("identifiability"),
    }
