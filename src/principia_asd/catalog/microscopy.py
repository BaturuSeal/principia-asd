"""Bounded MATLAB-5 magnetic-map reconstruction with source-coordinate custody.

The task is withheld-pixel interpolation, not temperature inversion or earthquake
forecasting. Original spatial-block partitions remain explicit diagnostic history.
"""

import struct
import zlib
from collections import Counter

import numpy as np

from ..io import contained, read_json
from .fracture import bounded_zip
from .splits import check_units

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
    **dict.fromkeys(["hx", "hy", "ox", "oy", "dg", "lo", "hi"], "source-native Bz unit"),
    "gx": "dimensionless local contrast",
    "gy": "dimensionless local contrast",
}
VARIABLES = {"Bt", "Bz", "corners", "h", "newLED", "step"}
MAX_ELEMENT = 19_000_000
MAX_FILE = 80_000_000


def _element(raw, at):
    """MAT-5 regular and four-byte small data elements; no nested objects."""
    if at + 8 > len(raw):
        raise ValueError("Truncated MAT element")
    first, size = struct.unpack_from("<II", raw, at)
    short_size = first >> 16
    if short_size:
        kind = first & 0xFFFF
        if short_size > 4:
            raise ValueError("Invalid MAT small element")
        return kind, memoryview(raw)[at + 4 : at + 4 + short_size], at + 8
    end = at + 8 + size
    aligned = end + (-size % 8)
    if size > MAX_ELEMENT or aligned > len(raw):
        raise ValueError("Oversized or truncated MAT element")
    return first, memoryview(raw)[at + 8 : end], aligned


def _matrix(raw):
    kind, data, end = _element(raw, 0)
    if kind != 14 or end != len(raw):
        raise ValueError("Expected exactly one MAT matrix")
    kind, flags, at = _element(data, 0)
    if kind != 6 or len(flags) != 8 or struct.unpack("<II", flags) != (6, 0):
        raise ValueError("Only real dense double MAT arrays are supported")
    kind, dims, at = _element(data, at)
    if kind != 5 or len(dims) != 8:
        raise ValueError("Expected two-dimensional MAT array")
    shape = struct.unpack("<ii", dims)
    if any(n <= 0 for n in shape) or shape[0] * shape[1] > 2_304_000:
        raise ValueError("Oversized or invalid MAT shape")
    kind, name, at = _element(data, at)
    if kind != 1:
        raise ValueError("Invalid MAT variable name")
    name = bytes(name).decode("ascii")
    if name not in VARIABLES:
        raise ValueError("Unexpected MAT variable")
    kind, values, at = _element(data, at)
    # MATLAB can pack integral-valued double-class geometry/LED arrays as uints.
    # Scientific Bz/Bt values and h/step must retain exact double storage.
    dtype = (
        "<f8"
        if kind == 9
        else "<u2"
        if name == "corners" and kind == 4
        else "u1"
        if name == "newLED" and kind == 2
        else None
    )
    if (
        dtype is None
        or len(values) != shape[0] * shape[1] * np.dtype(dtype).itemsize
        or at != len(data)
    ):
        raise ValueError("Invalid MAT numeric payload or hidden state")
    # Do not decode Bt/LED maps, inversion products or other response channels.
    array = (
        np.frombuffer(values, dtype=dtype).reshape(shape, order="F").astype(float, copy=True)
        if name in {"Bz", "corners", "h", "step"}
        else None
    )
    return name, shape, array


def stored_map(path):
    """Validate compressed byte and expanded allocation bounds before decoding."""
    if not 128 <= path.stat().st_size <= MAX_FILE:
        raise ValueError("Oversized or truncated microscopy MAT file")
    arrays, shapes, expanded = {}, {}, 0
    with path.open("rb") as stream:
        header = stream.read(128)
        if (
            not header.startswith(b"MATLAB 5.0 MAT-file")
            or header[116:124] != b"\x00" * 8
            or header[124:] != b"\x00\x01IM"
        ):
            raise ValueError("Unsupported MAT version, subsystem or byte order")
        for _ in range(6):
            tag = stream.read(8)
            if len(tag) != 8:
                raise ValueError("Missing microscopy MAT variable")
            kind, size = struct.unpack("<II", tag)
            if not 0 < size <= MAX_ELEMENT or kind not in {14, 15}:
                raise ValueError("Unsupported or oversized MAT top-level element")
            payload = stream.read(size)
            if len(payload) != size:
                raise ValueError("Truncated MAT payload")
            if kind == 15:
                decoder = zlib.decompressobj()
                try:
                    raw = decoder.decompress(payload, MAX_ELEMENT + 1)
                except zlib.error as exc:
                    raise ValueError("Corrupt MAT compression") from exc
                if (
                    len(raw) > MAX_ELEMENT
                    or not decoder.eof
                    or decoder.unused_data
                    or decoder.unconsumed_tail
                ):
                    raise ValueError("Oversized, incomplete or trailing MAT compression")
            else:
                padding = stream.read(-size % 8)
                raw = tag + payload + padding
            expanded += len(raw)
            if expanded > 57_000_000:
                raise ValueError("Oversized expanded microscopy file")
            name, shape, array = _matrix(raw)
            if name in shapes:
                raise ValueError("Duplicate MAT variable")
            shapes[name] = shape
            if array is not None:
                arrays[name] = array
        if stream.read(1) or shapes.keys() != VARIABLES:
            raise ValueError("Unexpected MAT variable inventory or trailing bytes")
    shape = shapes["Bz"]
    if shape != shapes["Bt"] or shape != shapes["newLED"] or min(shape) < 30:
        raise ValueError("Inconsistent microscopy map shapes")
    if shapes["corners"] != (2, 2) or shapes["h"] != (1, 1) or shapes["step"] != (1, 1):
        raise ValueError("Invalid microscopy geometry dimensions")
    if (
        not np.array_equal(arrays["corners"], [[1, 1], list(shape)])
        or not all(np.isfinite(arrays[k]).all() for k in ["h", "step"])
        or arrays["step"][0, 0] <= 0
        or arrays["h"][0, 0] < 0
    ):
        raise ValueError("Invalid microscopy geometry values")
    return arrays["Bz"], {
        "shape": list(shape),
        "native_h": float(arrays["h"][0, 0]),
        "native_step": float(arrays["step"][0, 0]),
        "corners": arrays["corners"].tolist(),
        "geometry_unit": "not encoded in MAT; no SI conversion asserted",
        "expanded_mat_bytes": expanded,
        "unused_variables": ["Bt", "newLED"],
        "nonfinite_map_pixels": int(np.sum(~np.isfinite(arrays["Bz"]))),
    }


def sampling_grid(shape):
    """Fixed lattice; prove target/predictor separation in pixel coordinates."""
    centers = [(y, x) for y in range(20, shape[0] - 8, 20) for x in range(20, shape[1] - 8, 20)]
    center_set, inputs = set(centers), set()
    for y, x in centers:
        for dy, dx in OFFSETS:
            point = (y + dy, x + dx)
            if point in center_set or not (0 <= point[0] < shape[0] and 0 <= point[1] < shape[1]):
                raise ValueError("Microscopy target alias or out-of-map predictor")
            if point in inputs:
                raise ValueError("Overlapping microscopy predictor stencils")
            inputs.add(point)
    return centers, {
        "target_centers": len(centers),
        "unique_predictor_pixels": len(inputs),
        "target_predictor_overlap": 0,
        "predictor_stencil_overlap": 0,
    }


def _source_readme(path):
    from .native import _xml

    with bounded_zip(path, max_bytes=200_000, max_member_bytes=100_000) as z:
        tree = _xml(z.read("word/document.xml"))
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        text = "\n".join(
            "".join(t.text or "" for t in p.iter(ns + "t")) for p in tree.iter(ns + "p")
        )
    for expected in [
        "CSH_FOV5_Bz_uz0.mat",
        "CSL_FOV4_Bz_uz0.mat",
        "119DOA",
        "129DOA",
        "MCMC parameter estimation",
    ]:
        if expected not in text:
            raise ValueError("Changed microscopy source description")
    return {
        "map_suffix_in_readme": "uz0",
        "registered_map_suffix": "uc0",
        "filename_discrepancy": "Preserved unresolved source suffix discrepancy; exact registered uc0 files are bound, not substituted",
    }


def reconstruct_microscopy(recipe, source_root):
    from .native import _registered_groups, _row, identity

    if (
        recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "source-native Bz unit (SI conversion unresolved)"
    ):
        raise ValueError("Changed microscopy unit declarations")
    assets = {a["role"]: a for a in recipe["assets"]}
    if len(assets) != len(recipe["assets"]) or assets.keys() != {
        "CSH_map",
        "CSL_map",
        "source_metadata",
        "source_readme",
    }:
        raise ValueError("Invalid microscopy asset inventory")
    meta = read_json(contained(source_root, assets["source_metadata"]["path"]))
    if (
        str(meta.get("id")) != "14776881"
        or meta.get("doi") != "10.5281/zenodo.14776881"
        or meta["metadata"]["license"]["id"] != "cc-by-4.0"
    ):
        raise ValueError("Changed microscopy source identity or rights metadata")
    readme = _source_readme(contained(source_root, assets["source_readme"]["path"]))
    case = recipe["scenario_id"]
    parts, lineage, diagnostics = {p: [] for p in ("train", "dev", "test")}, [], {}
    units, strip_units, observed = {}, {}, set()
    for specimen in ["CSH", "CSL"]:
        asset = assets[specimen + "_map"]
        a, metadata = stored_map(contained(source_root, asset["path"]))
        centers, separation = sampling_grid(a.shape)
        excluded = []
        for y, x in centers:
            yy = np.array([y] + [y + dy for dy, dx in OFFSETS])
            xx = np.array([x] + [x + dx for dy, dx in OFFSETS])
            z = a[yy, xx]
            if not np.isfinite(z).all():
                excluded.append(
                    {
                        "center": [y, x],
                        "nonfinite_offsets": np.flatnonzero(~np.isfinite(z)).tolist(),
                    }
                )
                continue
            group = f"{specimen}-r{y // 200:02d}-c{x // 320:02d}"
            split = recipe["group_assignments"].get(group)
            if split not in {"train", "dev", "test"} or ((specimen == "CSL") != (split == "test")):
                raise ValueError("Microscopy specimen/partition mismatch")
            observed.add(group)
            units[identity(case, "group", group)] = group
            strip_units[identity(case, "group", group)] = f"{specimen}-r{y // 200:02d}"
            u = z[1:]
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                scale = max(float(np.sqrt(np.mean(u * u))), 1e-15)
                values = {
                    "hx": (u[0] + u[1]) / 2,
                    "hy": (u[2] + u[3]) / 2,
                    "ox": (u[4] + u[5]) / 2,
                    "oy": (u[6] + u[7]) / 2,
                    "dg": float(np.mean(u[8:])),
                    "gx": abs(u[1] - u[0]) / scale,
                    "gy": abs(u[3] - u[2]) / scale,
                    "lo": float(min(u)),
                    "hi": float(max(u)),
                }
            row, trace = _row(
                case,
                f"{specimen}-{y}-{x}",
                group,
                split,
                values,
                z[0],
                {
                    "source": asset["path"],
                    "variable": "Bz",
                    "center_zero_based_yx": [y, x],
                    "predictor_offsets_ref": "microscopy_validation.predictor_offsets_zero_based_dy_dx",
                    "specimen": specimen,
                    "region": "FOV5" if specimen == "CSH" else "FOV4",
                    "spatial_block": group,
                    "calibration": "own twelve neighbors only; fixed RMS floor 1e-15; no fitted transform",
                },
            )
            parts[split].append(row)
            lineage.append(trace)
        diagnostics[specimen] = {
            **metadata,
            **separation,
            "excluded_nonfinite_stencils": excluded,
            "eligible_rows": len(centers) - len(excluded),
        }
    assignments = _registered_groups(recipe, observed)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "microscopy_validation": {
                "maps": diagnostics,
                "readme": readme,
                "spatial_blocks_by_split": dict(Counter(assignments.values())),
                "declared_whole_strip_check": check_units(parts, strip_units),
                "predictor_offsets_zero_based_dy_dx": [list(p) for p in OFFSETS],
                "fit_count": 0,
                "learned_transformations": [],
                "upstream_processing": "Stored magnetic Bz map; instrument reduction and field reconstruction not independently reproduced",
                "response_scope": "Withheld-pixel spatial interpolation at one acquisition; not temperature, earthquake prediction or a dynamical law",
                "exposure": "Retrospective and historically exposed; not independent confirmation",
            },
            "lineage_definition": {
                "coordinates": "Zero-based Bz[row,column]; transpose never inferred",
                "calibration": "Twelve fixed non-target pixels; no fitting, target normalization or temperature fields",
                "independent_unit": "CSH development specimen and CSL confirmation specimen; blocks/strips are spatial regions, not additional specimens",
            },
            "admission_blockers": [
                "Historical compact allocation splits declared whole development strips; a reviewed contract and new frozen cohort are required",
                "One development and one confirmation specimen do not support population-level earthquake claims",
                "Magnetic map processing, SI units, native h/step geometry and source filename discrepancy require clarification",
                "Source rights, notices and scientific contract require final review",
                "Upstream processing and feature operations excluded from historical rule complexity; sensitivity remains diagnostic",
            ],
        },
    )
