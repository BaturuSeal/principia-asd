"""Curator-only NOAA CRW native SSTA reconstruction; one-map spatial diagnostic.

The source is an already calibrated L4/climatological product. This reader does
not infer independent observations from geographic tiles or reproduce L4 fits.
"""

import hashlib
from collections import Counter
from pathlib import Path

import numpy as np

from ..io import contained
from .microwave import decoder
from .splits import check_units

PARSER = "coral-native-ssta-stencil-v1"
VARIABLE = "sea_surface_temperature_anomaly"
OFFSETS = (
    (0, -4),
    (0, 4),
    (-4, 0),
    (4, 0),
    (0, -8),
    (0, 8),
    (-8, 0),
    (8, 0),
    (-4, -4),
    (-4, 4),
    (4, -4),
    (4, 4),
)
INPUT_UNITS = {
    **dict.fromkeys(["hx", "hy", "ox", "oy", "dg", "gx", "gy"], "degree C"),
    "clat": "dimensionless cosine latitude",
}
ROOT_IDENTITY = {
    "id": "Satellite_Daily_Global_5km_SST_Anomaly",
    "product_version": "3.1",
    "time_coverage_start": "20260816T000000Z",
    "time_coverage_end": "20260817T000000Z",
    "processing_level": "Derived from L4 satellite sea surface temperaure analysis",
    "source": "Coral Reef Watch Daily Global 5km Satellite Sea Surface Temperature v3.1 (CoralTemp v3.1)",
}


def local_dataset(handle, name):
    """Deny indirect storage and optional decoder plugins before reading arrays."""
    h5py = decoder()
    if "/" in name or not isinstance(handle.get(name, getlink=True), h5py.HardLink):
        raise ValueError("External or indirect coral HDF5 link")
    ds = handle[name]
    if not isinstance(ds, h5py.Dataset) or ds.is_virtual or ds.external:
        raise ValueError("External, virtual or invalid coral dataset")
    filters = [
        ds.id.get_create_plist().get_filter(i)
        for i in range(ds.id.get_create_plist().get_nfilters())
    ]
    if any(
        not (
            (f[0] == 1 and len(f[2]) == 1 and 0 <= f[2][0] <= 9)
            or (f[0] == 2 and f[2] == (ds.dtype.itemsize,))
        )
        for f in filters
    ):
        raise ValueError("Unsupported coral compression filter")
    return ds


def text_attrs(obj, expected):
    for key, value in expected.items():
        actual = obj.attrs.get(key)
        if isinstance(actual, bytes):
            actual = actual.decode("utf-8")
        if not isinstance(actual, str) or actual != value:
            raise ValueError("Coral source identity, units or semantics differ: " + key)


def numeric_attrs(obj, expected):
    for key, value in expected.items():
        a = np.asarray(obj.attrs.get(key))
        if a.dtype.kind not in "iuf" or not np.array_equal(
            a.reshape(-1), np.asarray(value).reshape(-1)
        ):
            raise ValueError("Coral numeric metadata differs: " + key)


def native_arrays(path):
    h5py = decoder()
    if Path(path).stat().st_size > 30_000_000:
        raise ValueError("Oversized coral NetCDF file")
    inventory, arrays = [], {}
    with h5py.File(path, "r") as h:
        text_attrs(h, ROOT_IDENTITY)
        specs = [
            (VARIABLE, (1, 3600, 7200), "i", 2),
            ("mask", (1, 3600, 7200), "u", 1),
            ("lat", (3600,), "f", 4),
            ("lon", (7200,), "f", 4),
            ("time", (1,), "i", 4),
            ("crs", (), "i", 2),
        ]
        datasets = {}
        for name, shape, kind, width in specs:
            ds = local_dataset(h, name)
            if ds.shape != shape or ds.dtype.kind != kind or ds.dtype.itemsize != width:
                raise ValueError("Coral measurement shape or dtype differs")
            datasets[name] = ds
            inventory.append(
                {
                    "dataset": name,
                    "shape": list(shape),
                    "dtype": str(ds.dtype),
                    "expanded_bytes": int(ds.size * ds.dtype.itemsize),
                    "filters": [
                        int(ds.id.get_create_plist().get_filter(i)[0])
                        for i in range(ds.id.get_create_plist().get_nfilters())
                    ],
                }
            )
        text_attrs(datasets[VARIABLE], {"units": "degree_Celsius", "grid_mapping": "crs"})
        numeric_attrs(
            datasets[VARIABLE],
            {
                "scale_factor": [0.01],
                "_FillValue": [-32768],
                "valid_min": [-1500],
                "valid_max": [1500],
                "_Netcdf4Coordinates": [0, 2, 1],
            },
        )
        if "add_offset" in datasets[VARIABLE].attrs:
            numeric_attrs(datasets[VARIABLE], {"add_offset": [0]})
        text_attrs(
            datasets["mask"],
            {
                "units": "pixel_classification",
                "flag_meanings": "valid-water land missing ice",
                "coordinates": "time lat lon",
                "grid_mapping": "crs",
            },
        )
        numeric_attrs(
            datasets["mask"],
            {"flag_values": [0, 1, 2, 4], "_FillValue": [251], "_Netcdf4Coordinates": [0, 2, 1]},
        )
        for name, unit, axis in [
            ("lat", "degrees_north", "Y"),
            ("lon", "degrees_east", "X"),
            ("time", "seconds since 1981-01-01 00:00:00", "T"),
        ]:
            text_attrs(datasets[name], {"units": unit, "axis": axis})
        text_attrs(
            datasets["crs"], {"grid_mapping_name": "latitude_longitude", "epsg_code": "EPSG:4326"}
        )
        for name in ["lat", "lon", "time"]:
            arrays[name] = datasets[name][:]
        if (
            not np.array_equal(arrays["lat"], np.linspace(89.975, -89.975, 3600).astype("f4"))
            or not np.array_equal(arrays["lon"], np.linspace(-179.975, 179.975, 7200).astype("f4"))
            or arrays["time"].tolist() != [1439726400]
        ):
            raise ValueError("Coral coordinate grid or observation clock differs")
        arrays[VARIABLE], arrays["mask"] = datasets[VARIABLE][0], datasets["mask"][0]
        if not np.isin(arrays["mask"], [0, 1, 2, 4, 251]).all():
            raise ValueError("Undeclared coral quality mask")
    return arrays, inventory


def tile(lat, lon):
    # Keep the original float32 coordinate arithmetic and tile identities.
    return f"{int((lat + 90) // 20):02d}-{int((lon + 180) // 20):02d}"


def confirmation(group):
    h = hashlib.sha256(("P100-020-v1|" + group).encode()).hexdigest()
    return int(h[:8], 16) % 5 == 0


def sample_map(raw, mask, lat, lon):
    """Fixed lattice and twelve-neighbor operations, with explicit missingness."""
    if (
        raw.ndim != 2
        or mask.shape != raw.shape
        or lat.shape != (raw.shape[0],)
        or lon.shape != (raw.shape[1],)
        or not 40 <= raw.shape[0] <= 3600
        or not 40 <= raw.shape[1] <= 7200
        or raw.dtype.kind != "i"
        or mask.dtype.kind != "u"
        or not np.isfinite(lat).all()
        or not np.isfinite(lon).all()
        or np.any(abs(lat) > 90)
        or np.any(abs(lon) > 180)
    ):
        raise ValueError("Invalid or unbounded coral grid")
    records, reasons, mask_counts, candidates = [], Counter(), Counter(), 0
    for y in range(20, raw.shape[0], 40):
        if abs(lat[y]) > 60:
            continue
        for x in range(20, raw.shape[1], 40):
            candidates += 1
            yy = np.array([y] + [y + dy for dy, dx in OFFSETS])
            xx = np.array([x] + [x + dx for dy, dx in OFFSETS])
            if yy.min() < 0 or xx.min() < 0 or yy.max() >= len(lat) or xx.max() >= len(lon):
                raise ValueError("Coral stencil exceeds grid")
            z = raw[yy, xx].astype(float) * 0.01
            flags = mask[yy, xx]
            mask_counts.update(int(v) for v in flags)
            invalid = []
            if np.any(flags != 0):
                invalid.append("non_water_stencil")
            if not np.isfinite(z).all() or np.any(abs(z) > 15):
                invalid.append("invalid_or_fill_stencil")
            reasons.update(invalid)
            if invalid:
                continue
            u = z[1:]
            values = {
                "hx": (u[0] + u[1]) / 2,
                "hy": (u[2] + u[3]) / 2,
                "ox": (u[4] + u[5]) / 2,
                "oy": (u[6] + u[7]) / 2,
                "dg": float(np.mean(u[8:])),
                "gx": abs(u[1] - u[0]),
                "gy": abs(u[3] - u[2]),
                "clat": float(np.cos(np.deg2rad(lat[y]))),
            }
            records.append(
                {
                    "y": y,
                    "x": x,
                    "group": tile(lat[y], lon[x]),
                    "values": values,
                    "response": float(z[0]),
                    "latitude": float(lat[y]),
                    "longitude": float(lon[x]),
                    "neighbors": list(zip(yy[1:].tolist(), xx[1:].tolist(), strict=True)),
                    "neighbor_tiles": [
                        tile(lat[a], lon[b]) for a, b in zip(yy[1:], xx[1:], strict=True)
                    ],
                }
            )
    target_cells = {(r["y"], r["x"]) for r in records}
    input_cells = [cell for r in records for cell in r["neighbors"]]
    reused = len(input_cells) - len(set(input_cells))
    aliases = target_cells.intersection(input_cells)
    if aliases or reused:
        raise ValueError("Coral target alias or shared stencil pixel")
    return records, {
        "candidate_centers": candidates,
        "eligible_centers": len(records),
        "excluded_centers": candidates - len(records),
        "exclusion_reason_counts": dict(reasons),
        "candidate_stencil_mask_counts": dict(sorted(mask_counts.items())),
        "target_input_pixel_intersection": len(aliases),
        "reused_input_pixels": reused,
        "cross_tile_input_references": sum(
            t != r["group"] for r in records for t in r["neighbor_tiles"]
        ),
    }


def build_rows(recipe, records):
    from .native import _registered_groups, _row, identity

    groups = {r["group"] for r in records}
    assignments = _registered_groups(recipe, groups)
    if any((assignments[g] == "test") != confirmation(g) for g in groups):
        raise ValueError("Original coral confirmation allocation changed")
    source = next(a["path"] for a in recipe["assets"] if a["role"] == "coral_netcdf")
    parts, lineage = {p: [] for p in ("train", "dev", "test")}, []
    for r in sorted(records, key=lambda r: f"pixel-{r['y']}-{r['x']}"):
        group, label = r["group"], f"pixel-{r['y']}-{r['x']}"
        split = assignments[group]
        row, anchor = _row(
            recipe["scenario_id"],
            label,
            group,
            split,
            r["values"],
            r["response"],
            {
                "source": source,
                "dataset": VARIABLE,
                "time_index": 0,
                "response_pixel": [r["y"], r["x"]],
                "stencil_id": PARSER,
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "geographic_tile": group,
                "linked_unit": "one-map-2026-08-16",
            },
        )
        parts[split].append(row)
        lineage.append(anchor)
    return (
        parts,
        lineage,
        check_units(parts, {identity(recipe["scenario_id"], "group", g): g for g in groups}),
    )


def reconstruct_coral(recipe, source_root):
    if recipe["input_units"] != INPUT_UNITS or recipe["output_units"] != "degree C":
        raise ValueError("Coral recipe units differ")
    (asset,) = [a for a in recipe["assets"] if a["role"] == "coral_netcdf"]
    arrays, inventory = native_arrays(contained(source_root, asset["path"]))
    records, diagnostics = sample_map(
        arrays[VARIABLE], arrays["mask"], arrays["lat"], arrays["lon"]
    )
    parts, lineage, split = build_rows(recipe, records)
    validation = {
        **diagnostics,
        "native_inventory": inventory,
        "source_identity": ROOT_IDENTITY,
        "observation_reference_seconds_since_1981": int(arrays["time"][0]),
        "lineage_recipe": {
            "stencil_id": PARSER,
            "input_coordinates": "response_pixel plus each ordered offset",
            "time_index": 0,
            "scale_factor": 0.01,
            "response_and_inputs_dataset": VARIABLE,
        },
        "grid_spacing_degrees": 0.05,
        "sampling_stride_pixels": 40,
        "offsets": [list(p) for p in OFFSETS],
        "groups": len(recipe["group_assignments"]),
        "groups_by_partition": dict(Counter(recipe["group_assignments"].values())),
        "local_preprocessing_fits": 0,
        "discovery_rule_fits": 0,
        "upstream_preprocessing": "Source L4 SST analysis and 1991-2020 climatology are inherited; upstream fitting, calibration and spatial dependence are not reproduced or counted as zero",
        "independence_scope": "Whole 20-degree tiles within one spatially dependent daily map; no independent temporal replicates",
        "response_scope": "Same-date anomaly interpolation, not temperature forecasting, bleaching prediction or causal discovery",
        "selection_scope": "Retrospective target-and-neighbor quality/range eligibility; missing centers are not imputed",
    }
    return (
        parts,
        lineage,
        {
            "split_check": split,
            "coral_validation": validation,
            "admission_blockers": [
                "Single already processed daily map; upstream climatology and calibration remain external state",
                "Retrospective target quality selection and spatial dependence limit inference",
                "Final scientific contract, source citation/notice and rights review pending",
            ],
        },
    )
