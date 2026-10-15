"""Curator-only KTH/HWAT XML reconstruction with explicit water properties.

Densities are pressure-derived IAPWS SR1-86(1992) approximations, not measured
responses or learned primitives. Radial coordinates are normalized by the sampled
maximum, not a verified tube radius. Historical same-day dependence is retained.
"""

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np

from ..io import contained, sha
from .splits import check_units

INPUT_UNITS = {
    "pressure_Pa": "Pa, absolute",
    "massflux_kg_m2_s": "kg m^-2 s^-1",
    "quality": "kg vapor per kg mixture",
    "radial_fraction": "dimensionless native coordinate / maximum sampled coordinate",
    "rho_liquid": "kg m^-3",
    "rho_vapor": "kg m^-3",
}
TOP_SCALARS = {
    "ID",
    "RUN",
    "TIN",
    "PRESSURE",
    "MASSFLOW",
    "MASSFLUX",
    "POWER",
    "HEATFLUX",
    "XIN",
    "XOUT",
    "HOUT",
    "DISPERSEDPHASE",
}
RADIAL_SCALARS = {
    "RADIUS",
    "VOIDFRACTION",
    "DYNPRESSURE",
    "VELOCITY",
    "NUMBERMEANDIAMETER",
    "SURFACEMEANDIAMETER",
    "VOLUMEMEANDIAMETER",
}
RADIAL_ARRAYS = {"DIAMETER", "NUMBERDENSITY", "SURFACEDENSITY", "VOLUMEDENSITY"}
HELD = {"ID_20230630_Run_31", "ID_20230630_Run_32", "ID_20230809_Run_09"}

# Wagner and Pruss (1993), doi:10.1063/1.555926, appendix equations 1--3.
# Public scientific constants; independently implemented, no IAPWS package copied.
TC, PC, RHOC = 647.096, 22_064_000.0, 322.0
PRESSURE_COEFFICIENTS = np.array(
    [-7.85951783, 1.84408259, -11.7866497, 22.6807411, -15.9618719, 1.80122502]
)
PRESSURE_POWERS = np.array([1, 1.5, 3, 3.5, 4, 7.5])
LIQUID_COEFFICIENTS = np.array(
    [1.99274064, 1.09965342, -0.510839303, -1.75493479, -45.5170352, -674694.45]
)
LIQUID_POWERS = np.array([1 / 3, 2 / 3, 5 / 3, 16 / 3, 43 / 3, 110 / 3])
VAPOR_COEFFICIENTS = np.array(
    [-2.0315024, -2.6830294, -5.38626492, -17.2991605, -44.7586581, -63.9201063]
)
VAPOR_POWERS = np.array([1 / 3, 2 / 3, 4 / 3, 3, 37 / 6, 71 / 6])


def saturation_pressure(temperature):
    if not math.isfinite(temperature) or not 273.16 <= temperature <= TC:
        raise ValueError("Temperature outside IAPWS saturation domain")
    q = 1 - temperature / TC
    return float(PC * np.exp(TC / temperature * np.sum(PRESSURE_COEFFICIENTS * q**PRESSURE_POWERS)))


def saturation(pressure):
    """Fixed 80-step inverse pressure calculation; zero response calibration."""
    if not math.isfinite(pressure) or not 611.657 <= pressure <= PC:
        raise ValueError("Pressure outside IAPWS saturation domain")
    if pressure == PC:
        return TC, RHOC, RHOC
    lo, hi = 273.16, 647.095999
    for _ in range(80):
        middle = (lo + hi) / 2
        if saturation_pressure(middle) < pressure:
            lo = middle
        else:
            hi = middle
    temperature = (lo + hi) / 2
    q = 1 - temperature / TC
    liquid = float(RHOC * (1 + np.sum(LIQUID_COEFFICIENTS * q**LIQUID_POWERS)))
    vapor = float(RHOC * np.exp(np.sum(VAPOR_COEFFICIENTS * q**VAPOR_POWERS)))
    if not 0 < vapor <= liquid or not math.isclose(
        saturation_pressure(temperature), pressure, rel_tol=1e-6
    ):
        raise ValueError("Invalid saturated water property reconstruction")
    return temperature, liquid, vapor


def scalar(element, name, *, numeric=True):
    nodes = element.findall(name)
    if len(nodes) != 1 or list(nodes[0]) or nodes[0].attrib or nodes[0].text is None:
        raise ValueError("Missing, duplicate or structured boiling scalar: " + name)
    value = nodes[0].text.strip()
    if not numeric:
        return value
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Nonfinite boiling scalar: " + name)
    return value


def stored_run(raw, group):
    from .native import _xml

    if len(raw) > 1_000_000:
        raise ValueError("Oversized boiling XML acquisition")
    match = re.fullmatch(r"ID_([0-9]{8})_Run_([0-9]{2})", group)
    if not match:
        raise ValueError("Invalid boiling run identity")
    date = datetime.strptime(match[1], "%Y%m%d").date().isoformat()
    root = _xml(raw)
    counts = Counter(n.tag for n in root)
    if (
        root.tag != group
        or root.attrib
        or set(counts) != TOP_SCALARS | {"pressuredrop", "walltemperature", "radial"}
        or any(counts[k] != 1 for k in TOP_SCALARS | {"pressuredrop", "walltemperature"})
        or counts["radial"] != 12
        or sum(1 for _ in root.iter()) > 12_000
    ):
        raise ValueError("Changed boiling XML identity or channel inventory")
    if scalar(root, "ID", numeric=False) != match[1] or scalar(root, "RUN") != int(match[2]):
        raise ValueError("Boiling file/header run identity differs")
    pressure, flux, quality = (scalar(root, n) for n in ["PRESSURE", "MASSFLUX", "XOUT"])
    if not 0 < flux <= 10_000 or not 0 <= quality <= 1:
        raise ValueError("Boiling flux or supplied quality outside declared domain")
    temperature, liquid, vapor = saturation(pressure)
    phase = scalar(root, "DISPERSEDPHASE", numeric=False)
    if phase not in {"liquid", "vapor"}:
        raise ValueError("Unknown source dispersed-phase label")
    values, inventory = [], Counter()
    for radial in root.findall("radial"):
        tags = Counter(n.tag for n in radial)
        if (
            radial.attrib
            or not {"RADIUS", "VOIDFRACTION"} <= tags.keys()
            or not tags.keys() <= RADIAL_SCALARS | RADIAL_ARRAYS
            or any(tags[k] != 1 for k in tags.keys() & RADIAL_SCALARS)
            or (tags.keys() & RADIAL_ARRAYS and any(tags[k] != 200 for k in RADIAL_ARRAYS))
        ):
            raise ValueError("Malformed boiling radial channel inventory")
        radius, response = scalar(radial, "RADIUS"), scalar(radial, "VOIDFRACTION")
        if radius <= 0 or not 0 <= response <= 1:
            raise ValueError("Invalid boiling coordinate or void fraction")
        values.append((radius, response))
        inventory.update(tags)
    radii = [v[0] for v in values]
    if any(b >= a for a, b in zip(radii, radii[1:], strict=False)):
        raise ValueError("Repeated or reordered boiling radial coordinate")
    maximum = max(radii)
    features = {
        "pressure_Pa": pressure,
        "massflux_kg_m2_s": flux,
        "quality": quality,
        "rho_liquid": liquid,
        "rho_vapor": vapor,
    }
    info = {
        "group": group,
        "source_date": date,
        "source_phase_stratum": phase,
        "radial_records": len(values),
        "radial_channel_cells": dict(sorted(inventory.items())),
        "native_coordinate_maximum": maximum,
        "native_coordinate_unit": "unresolved; only dimensionless ratio exported",
        "saturation_temperature_K": temperature,
        "pressure_Pa": pressure,
        "derived_rho_liquid_kg_m3": liquid,
        "derived_rho_vapor_kg_m3": vapor,
        "pressure_inversion_iterations": 80,
        "saturation_pressure_residual_Pa": saturation_pressure(temperature) - pressure,
        "ignored_root_channels": sorted(
            TOP_SCALARS - {"ID", "RUN", "PRESSURE", "MASSFLUX", "XOUT"}
        ),
        "source_root_children": dict(sorted(counts.items())),
    }
    return values, features, info


def original_assignments(case, groups):
    from .native import identity

    if not HELD <= groups or len(groups) != 12:
        raise ValueError("Incomplete boiling run cohort")
    ordered = sorted(
        groups - HELD, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)])
    )
    dev = set(ordered[: max(2, len(ordered) // 5)])
    return {g: "test" if g in HELD else "dev" if g in dev else "train" for g in groups}


def reconstruct_boiling(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (meta_asset,) = [a for a in recipe["assets"] if a["role"] == "zenodo_record"]
    (readme_asset,) = [a for a in recipe["assets"] if a["role"] == "source_readme"]
    sources = [a for a in recipe["assets"] if a["role"] == "boiling_run"]
    meta = json.loads(
        contained(source_root, meta_asset["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    readme = contained(source_root, readme_asset["path"]).read_text()
    if (
        str(meta["id"]) != "14627088"
        or meta["doi"] != "10.5281/zenodo.14627088"
        or "SI units have been used" not in readme
        or "inlet and wall temperatures" not in readme
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "dimensionless"
    ):
        raise ValueError("Boiling source identity or unit policy differs")
    groups = {contained(source_root, a["path"]).stem for a in sources}
    assignments = _registered_groups(recipe, groups)
    if len(sources) != len(groups) or assignments != original_assignments(
        recipe["scenario_id"], groups
    ):
        raise ValueError("Frozen whole-run boiling allocation differs")
    parts, lineage, units, runs = {p: [] for p in ("train", "dev", "test")}, [], {}, []
    dates = defaultdict(set)
    strata = defaultdict(list)
    for asset in sorted(sources, key=lambda a: a["path"]):
        path = contained(source_root, asset["path"])
        group, split = path.stem, assignments[path.stem]
        values, features, info = stored_run(path.read_bytes(), group)
        dates[info["source_date"]].add(split)
        strata[info["source_phase_stratum"]].append(group)
        info.update({"split": split, "source": asset["path"]})
        runs.append(info)
        units[identity(recipe["scenario_id"], "group", group)] = group
        for j, (radius, response) in enumerate(values, 1):
            row, origin = _row(
                recipe["scenario_id"],
                f"{group}:radial{j:02d}",
                group,
                split,
                {**features, "radial_fraction": radius / info["native_coordinate_maximum"]},
                response,
                {
                    "source": asset["path"],
                    "source_radial_index_1based": j,
                    "xml_path": f"/{group}/radial[{j}]/VOIDFRACTION",
                    "coordinate_path": f"/{group}/radial[{j}]/RADIUS",
                    "coordinate_normalization": "RADIUS/max(all 12 sampled RADIUS values)",
                    "property_source": "IAPWS SR1-86(1992), equations 1-3; pressure only",
                },
            )
            parts[split].append(row)
            lineage.append(origin)
    # Phase labels enter only validation of the original stratified allocation.
    held = set()
    for phase, names in strata.items():
        ordered = sorted(
            names,
            key=lambda g: hashlib.sha256(
                ("principia-asd-pilot2-20260930-v1|" + g).encode()
            ).hexdigest(),
        )
        held.update(ordered[: 2 if phase == "liquid" else 1])
    if held != HELD or {k: len(v) for k, v in strata.items()} != {"liquid": 9, "vapor": 3}:
        raise ValueError("Historical boiling stratum identity changed")
    shared_dates = {d: sorted(ps) for d, ps in sorted(dates.items()) if len(ps) > 1}
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "native_runs": runs,
            "boiling_validation": {
                "runs": len(runs),
                "radial_measurements": sum(r["radial_records"] for r in runs),
                "source_dates": len(dates),
                "shared_source_dates": shared_dates,
                "group_counts": {p: sum(a == p for a in assignments.values()) for p in parts},
                "density_evaluations": len(runs),
                "bisection_iterations": 80 * len(runs),
                "fit_count": 0,
                "target_calibration_count": 0,
                "ignored_radial_distribution_cells": sum(
                    sum(r["radial_channel_cells"].get(k, 0) for k in RADIAL_ARRAYS) for r in runs
                ),
                "response_scope": "Stored local VOIDFRACTION; no raw probe-signal reprocessing",
                "density_scope": "Pressure-derived saturated-water approximation; not independently measured densities",
                "no_response_derived_predictors": True,
            },
            "admission_blockers": [
                "Single facility and same-day runs cross splits; independent day/calibration transfer is not established",
                "Supplied outlet quality sensor/energy-balance provenance requires confirmation",
                "Native radial unit and true tube-radius normalization remain unverified",
                "Raw probe processing, scientific contract, perturbation model and final rights/attribution review pending",
                "Historical complexity counts the submitted rule only, excluding upstream pressure-property preparation; full-pipeline complexity is not assessed",
            ],
        },
    )
