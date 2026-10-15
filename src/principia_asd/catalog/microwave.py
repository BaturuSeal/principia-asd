"""Native, curator-only pump extrapolation; no inverse-model or notebook execution."""

import json
from pathlib import Path

import numpy as np

from ..io import contained, file_sha, sha
from .splits import check_units

PARSER = "microwave-native-usb-matrices-v1"
GROUP = "Scattering/2025-11-21_16_40_49"
INPUT_UNITS = {
    "g": "fsu;pumpamplitudecontrol",
    "ghi": "fsu;highcalibrationpumpcontrol",
    "glo": "fsu;lowpumpcontrol",
    "hi": "fsu;secondcalibrationresponse",
    "lo": "fsu;lowpumpamplituderesponse",
    "noise": "fsu;zero-pumpresponse",
    "r": "dimensionless normalizedpumpincrement",
    "sep": "integer frequency-bin separation;100kHzbins",
}
# Exact native axes. Singleton dimensions are verified, not guessed by squeeze.
SPECS = {
    "USB": ((1, 51, 1, 1, 1, 13, 13), "c", 16, "fsu complex"),
    "amp fc pumps": ((51,), "f", 8, "fsu"),
    "freq sig": ((1, 13), "f", 8, "Hz"),
    "freq fc pumps": ((1, 12), "f", 8, "Hz"),
    "freq param pumps": ((1, 0), "f", 8, "Hz"),
    "amp param pumps": ((1,), "f", 8, "fsu"),
    "phase fc pumps": ((1,), "f", 8, "rad"),
    "phase param pumps": ((1,), "f", 8, "rad"),
    "df": ((1,), "f", 8, "Hz"),
    "pumping scheme": ((), "i", 8, "int"),
}


def decoder():
    try:
        import h5py
    except ImportError as exc:
        raise RuntimeError(
            "Native HDF5 preparation requires principia-asd[curation] in a separate curator environment"
        ) from exc
    return h5py


def decoder_binding():
    h5py = decoder()
    return {
        "h5py": h5py.__version__,
        "hdf5": h5py.version.hdf5_version,
        "h5py_core_sha256": file_sha(Path(h5py.h5.__file__)),
    }


def native_arrays(path):
    """Read only local, bounded, unfiltered datasets; reject external/VDS access."""
    h5py = decoder()
    if Path(path).stat().st_size > 2_000_000:
        raise ValueError("Oversized microwave HDF5 source")
    arrays, inventory = {}, []
    with h5py.File(path, "r") as h:
        group = h
        for component in GROUP.split("/"):
            if not isinstance(group.get(component, getlink=True), h5py.HardLink):
                raise ValueError("External or indirect HDF5 group")
            group = group[component]
            if not isinstance(group, h5py.Group):
                raise ValueError("Wrong HDF5 acquisition group type")
        for name, (shape, kind, width, unit) in SPECS.items():
            if not isinstance(group.get(name, getlink=True), h5py.HardLink):
                raise ValueError("External or indirect HDF5 dataset")
            d = group[name]
            if not isinstance(d, h5py.Dataset):
                raise ValueError("Missing native microwave measurement dataset")
            if (
                d.shape != shape
                or d.dtype.kind != kind
                or d.dtype.itemsize != width
                or d.is_virtual
                or d.external
                or d.id.get_create_plist().get_nfilters()
            ):
                raise ValueError("Unsupported HDF5 shape, dtype, external storage or filters")
            if d.attrs.get("Unit") != unit:
                raise ValueError("Native microwave measurement units differ")
            a = d[()]
            if not np.isfinite(a).all():
                raise ValueError("Nonfinite microwave source; no cohort filtering")
            arrays[name] = a
            inventory.append(
                {
                    "dataset": GROUP + "/" + name,
                    "shape": list(shape),
                    "dtype": str(d.dtype),
                    "unit": unit,
                    "values": int(d.size),
                }
            )
    amp, freq = arrays["amp fc pumps"], arrays["freq sig"][0]
    if not np.allclose(amp, np.r_[0.0, np.linspace(0.13, 0.18, 50)], rtol=0, atol=1e-14):
        raise ValueError("Pump control grid differs from registered acquisition")
    expected = {
        "freq sig": (4_199_400_000 + 100_000 * np.arange(13))[None, :],
        "freq fc pumps": (100_000 * np.arange(1, 13))[None, :],
        "amp param pumps": np.array([1.0]),
        "phase fc pumps": np.array([0.0]),
        "phase param pumps": np.array([0.0]),
        "df": np.array([100_000.0]),
        "pumping scheme": np.array(13),
    }
    if any(not np.array_equal(arrays[k], v) for k, v in expected.items()):
        raise ValueError("Frequency, phase or acquisition control identity differs")
    return arrays["USB"][0, :, 0, 0, 0, :, :], amp, freq, inventory


def original_assignments(case):
    from .native import identity

    groups = [f"pump-{i:02d}" for i in range(12, 51)]
    dev = set(
        sorted(groups[:29], key=lambda g: sha(["compact-v2", case, identity(case, "group", g)]))[:5]
    )
    return {g: "test" if int(g[-2:]) >= 41 else "dev" if g in dev else "train" for g in groups}


def reconstruct_microwave(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "microwave_hdf5"]
    (meta,) = [a for a in recipe["assets"] if a["role"] == "source_metadata"]
    (readme,) = [a for a in recipe["assets"] if a["role"] == "source_readme"]
    metadata = json.loads(
        contained(source_root, meta["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    text = contained(source_root, readme["path"]).read_text()
    if (
        metadata["id"] != 18938314
        or metadata["doi"] != "10.5281/zenodo.18938314"
        or metadata["metadata"]["license"]["id"] != "cc-by-4.0"
        or metadata["metadata"]["version"] != "1.0"
        or "'2025-11-21_16_40_49'" not in text
        or "Dataset to create Fig.4" not in text
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "fsu; instrument full-scale units"
    ):
        raise ValueError("Microwave source identity, license, version or units differ")
    groups = original_assignments(recipe["scenario_id"])
    if _registered_groups(recipe, groups) != groups:
        raise ValueError("Historical whole-pump matrix assignments changed")
    u, amp, freq, inventory = native_arrays(contained(source_root, asset["path"]))
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    for k in range(12, 51):
        group = f"pump-{k:02d}"
        split = groups[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        for a in range(13):
            for b in range(13):
                if a == b:
                    continue
                # Preserve scalar complex magnitude's exact historical operation order.
                values = {
                    "lo": float(abs(u[1, a, b])),
                    "hi": float(abs(u[11, a, b])),
                    "noise": float(abs(u[0, a, b])),
                    "r": float((amp[k] - amp[1]) / (amp[11] - amp[1])),
                    "g": float(amp[k]),
                    "glo": float(amp[1]),
                    "ghi": float(amp[11]),
                    "sep": float(abs(a - b)),
                }
                row, anchor = _row(
                    recipe["scenario_id"],
                    group + f"-edge-{a:02d}-{b:02d}",
                    group,
                    split,
                    values,
                    abs(u[k, a, b]),
                    {
                        "source": asset["path"],
                        "dataset": GROUP + "/USB",
                        "native_zero_based_index": [0, k, 0, 0, 0, a, b],
                        "calibration_pump_indices": [0, 1, 11],
                        "frequency_pair_Hz": [float(freq[a]), float(freq[b])],
                        "direction": "native last-two-axis order; not symmetrized or transposed",
                    },
                )
                parts[split].append(row)
                lineage.append(anchor)
    checks = {
        "split_check": check_units(parts, units),
        "microwave_validation": {
            "dataset_inventory": inventory,
            "decoder": decoder_binding(),
            "native_complex_values": int(u.size),
            "eligible_rows": 6084,
            "directed_pairs_per_matrix": 156,
            "calibration_matrices": [0, 1, 11],
            "calibration_complex_values": 468,
            "unscored_noncalibration_pump_indices": list(range(2, 11)),
            "diagonal_values_excluded": 663,
            "group_counts": {s: list(groups.values()).count(s) for s in parts},
            "target_pump_range": [float(amp[12]), float(amp[50])],
            "test_pump_range": [float(amp[41]), float(amp[50])],
            "signal_frequency_Hz": freq.tolist(),
            "phase_policy": "Native complex arrays decoded; magnitude target discards phase without a reciprocity assumption",
            "source_std_used": False,
            "fit_count": 0,
            "learned_transformations": [],
            "physical_replicates": "One installation/acquisition; pump matrices are linked conditions, not independent devices",
            "legacy_five_folds_not_used_in_compact_split": True,
        },
        "admission_blockers": [
            "One installation/acquisition; shared directed-pair calibration does not establish independent-device transfer",
            "Frequency-control extrapolation in source full-scale units; SI amplitude/power and input/output axis orientation not independently certified",
            "Magnitude-only target does not recover complex phase, pump mechanism or the inverse control problem",
            "USB export is an upstream measured/reduced response; detector processing and USB std uncertainty not independently validated",
            "Rule-only complexity excludes complex magnitudes and calibrated input construction",
            "Rights/notices, calibrated perturbations and final scientific admission pending",
        ],
    }
    return parts, lineage, checks
