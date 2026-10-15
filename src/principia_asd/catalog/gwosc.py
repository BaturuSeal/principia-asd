"""Curator-only GWOSC H1 spectral-summary reconstruction and mask audit.

Fixed historical eligibility is DATA plus injection bits 0/1/2/4. It does not
require the continuous-wave injection veto, or all higher data-quality bits.
"""

from collections import Counter
from pathlib import Path

import numpy as np
from scipy.signal import welch

from ..io import contained
from .microwave import decoder
from .splits import check_units

PARSER = "gwosc-native-causal-spectral-windows-v1"
GPS = 1388511232
FS = 4096
WINDOW = 16
SAMPLES = FS * WINDOW
DURATION = 4096
INPUTS = ["lag1", "lag2", "lag3", "lag4", "median4", "mad4", "low1", "high1", "line1"]
INPUT_UNITS = dict.fromkeys(INPUTS, "RMS strain in units of 1e-21")
OUTPUT_UNITS = "10^-21 strain"
DQ_NAMES = [
    "DATA",
    "CBC_CAT1",
    "CBC_CAT2",
    "CBC_CAT3",
    "BURST_CAT1",
    "BURST_CAT2",
    "BURST_CAT3",
    "STOCH_CAT1",
    "CW_CAT1",
]
INJ_NAMES = [
    "NO_CBC_HW_INJ",
    "NO_BURST_HW_INJ",
    "NO_DETCHAR_HW_INJ",
    "NO_CW_HW_INJ",
    "NO_STOCH_HW_INJ",
]
BANDS = [(30, 80), (10, 30), (80, 200), (59, 61)]


def local_dataset(handle, path):
    """Preflight each path component before dereferencing; no indirect storage."""
    h5py = decoder()
    group = handle
    components = path.split("/")
    for i, component in enumerate(components):
        if not isinstance(group.get(component, getlink=True), h5py.HardLink):
            raise ValueError("External or indirect GWOSC HDF5 link")
        item = group[component]
        if i < len(components) - 1:
            if not isinstance(item, h5py.Group):
                raise ValueError("Invalid GWOSC HDF5 group")
            group = item
    if not isinstance(item, h5py.Dataset) or item.is_virtual or item.external:
        raise ValueError("External, virtual or invalid GWOSC dataset")
    # Only built-in deflate and checksum filters. No dynamic filter plugin loads.
    filters = [
        item.id.get_create_plist().get_filter(i)
        for i in range(item.id.get_create_plist().get_nfilters())
    ]
    if any(
        not (
            (f[0] == 1 and f[2] and len(f[2]) == 1 and 0 <= f[2][0] <= 9)
            or (f[0] == 3 and not f[2])
        )
        for f in filters
    ):
        raise ValueError("Unsupported GWOSC compression filter")
    return item


def text_values(handle, path, expected):
    h5py = decoder()
    ds = local_dataset(handle, path)
    shape = (len(expected),) if isinstance(expected, list) else ()
    if ds.shape != shape or h5py.check_string_dtype(ds.dtype) is None:
        raise ValueError("Invalid GWOSC text schema")
    values = ds.asstr()[()]
    if (values.tolist() if isinstance(values, np.ndarray) else values) != expected:
        raise ValueError("GWOSC source identity or mask semantics differ: " + path)


def native_arrays(path):
    h5py = decoder()
    if Path(path).stat().st_size > 150_000_000:
        raise ValueError("Oversized GWOSC HDF5 file")
    arrays, inventory = {}, []
    with h5py.File(path, "r") as h:
        for key, value in {"GPSstart": GPS, "Duration": DURATION}.items():
            ds = local_dataset(h, "meta/" + key)
            if ds.shape != () or ds.dtype.kind not in "iu" or int(ds[()]) != value:
                raise ValueError("GWOSC acquisition origin/duration differs")
        for key, value in {
            "Detector": "H1",
            "Observatory": "H",
            "Type": "StrainTimeSeries",
            "UTCstart": "2024-01-05T17:33:34",
            "FrameType": "H1_HOFT_C00_AR",
            "StrainChannel": "H1:GDS-CALIB_STRAIN_CLEAN_AR",
        }.items():
            text_values(h, "meta/" + key, value)
        text_values(h, "quality/simple/DQShortnames", DQ_NAMES)
        text_values(h, "quality/injections/InjShortnames", INJ_NAMES)
        text_values(h, "strain/GWOSCmeta", "GWOSC-4KHZ_R1_STRAIN")
        specs = [
            ("strain/Strain", DURATION * FS, "f", 8, 1 / FS, "Strain", None),
            ("quality/simple/DQmask", DURATION, "u", 4, 1.0, "DQmask", 9),
            ("quality/injections/Injmask", DURATION, "u", 4, 1.0, "Injmask", 5),
        ]
        for name, count, kind, width, spacing, label, bits in specs:
            ds = local_dataset(h, name)
            if ds.shape != (count,) or ds.dtype.kind != kind or ds.dtype.itemsize != width:
                raise ValueError("GWOSC measurement shape or dtype differs")
            attrs = {
                "Npoints": count,
                "Xstart": GPS,
                "Xspacing": spacing,
                "Xunits": "second",
                "Xlabel": "GPS time",
                "Ylabel": label,
            }
            attrs.update({"Bits": bits} if bits else {"Yunits": ""})
            if any(ds.attrs.get(k) != v for k, v in attrs.items()):
                raise ValueError("GWOSC clock, mask count or units differ")
            a = ds[:]
            if bits and np.any(a >= 2**bits):
                raise ValueError("Undeclared GWOSC quality bits")
            arrays[label] = a
            inventory.append(
                {
                    "dataset": name,
                    "shape": list(ds.shape),
                    "dtype": str(ds.dtype),
                    "spacing_seconds": spacing,
                    "gps_start": GPS,
                    "values": count,
                    "filters": [
                        int(ds.id.get_create_plist().get_filter(i)[0])
                        for i in range(ds.id.get_create_plist().get_nfilters())
                    ],
                }
            )
    return arrays, inventory


def summarize(strain, quality, injections):
    """Fixed nonoverlapping windows; all spectral operations remain expanded."""
    if (
        strain.ndim != 1
        or quality.ndim != 1
        or injections.shape != quality.shape
        or len(quality) % WINDOW
        or len(strain) != len(quality) * FS
        or not 5 * WINDOW <= len(quality) <= DURATION
        or quality.dtype.kind not in "iu"
        or injections.dtype.kind not in "iu"
    ):
        raise ValueError("Unaligned or unbounded GWOSC sample clocks")
    summaries, diagnostics = {}, []
    for k in range(len(quality) // WINDOW):
        seconds = slice(k * WINDOW, (k + 1) * WINDOW)
        x = strain[k * SAMPLES : (k + 1) * SAMPLES]
        dq, inj = quality[seconds], injections[seconds]
        reasons = []
        if not np.all((dq & 1) > 0):
            reasons.append("missing_DATA_flag")
        if not np.all((inj & 23) == 23):
            reasons.append("required_injection_veto_unavailable")
        if not np.isfinite(x).all():
            reasons.append("nonfinite_strain")
        diagnostics.append(
            {
                "window_index": k,
                "exclusion_reasons": reasons,
                "quality_bitwise_and": int(np.bitwise_and.reduce(dq)),
                "injection_bitwise_and": int(np.bitwise_and.reduce(inj)),
                "quality_bit_counts": [int(np.count_nonzero(dq & (1 << b))) for b in range(9)],
                "injection_bit_counts": [int(np.count_nonzero(inj & (1 << b))) for b in range(5)],
            }
        )
        if reasons:
            continue
        f, power = welch(
            x * 1e21, fs=FS, nperseg=8192, noverlap=4096, window="hann", detrend="constant"
        )
        bands = []
        for low, high in BANDS:
            selected = (f >= low) & (f <= high)
            # scipy.integrate/numpy.trapezoid defaults share the same trapezoid operations.
            integral = np.sum(
                np.diff(f[selected]) * (power[selected][1:] + power[selected][:-1]) / 2.0
            )
            bands.append(float(np.sqrt(integral)))
        if not np.isfinite(bands).all():
            raise ValueError("Invalid GWOSC spectral reduction")
        summaries[k] = bands
    return summaries, diagnostics


def build_rows(recipe, summaries):
    from .native import _registered_groups, _row, identity

    indices = [k for k in range(4, 256) if all(k - i in summaries for i in range(5))]
    groups = {f"block{k // 32}" for k in indices}
    assignments = _registered_groups(recipe, groups)
    if any((assignments[g] == "test") != (int(g[5:]) >= 6) for g in groups):
        raise ValueError("Original GWOSC confirmation boundary changed")
    parts, lineage = {p: [] for p in ("train", "dev", "test")}, []
    source = next(a["path"] for a in recipe["assets"] if a["role"] == "gwosc_hdf5")
    for k in sorted(indices, key=lambda k: "H1:w" + str(k)):
        past = np.array([summaries[k - i][0] for i in range(1, 5)])
        median = float(np.median(past))
        values = {
            **{f"lag{i}": float(past[i - 1]) for i in range(1, 5)},
            "median4": median,
            "mad4": float(np.median(abs(past - median))),
            "low1": summaries[k - 1][1],
            "high1": summaries[k - 1][2],
            "line1": summaries[k - 1][3],
        }
        group, split = f"block{k // 32}", assignments[f"block{k // 32}"]
        row, anchor = _row(
            recipe["scenario_id"],
            "H1:w" + str(k),
            group,
            split,
            values,
            summaries[k][0],
            {
                "source": source,
                "dataset": "strain/Strain",
                "window_index": k,
                "response_slice": [k * SAMPLES, (k + 1) * SAMPLES],
                "input_slices": [[(k - i) * SAMPLES, (k - i + 1) * SAMPLES] for i in range(1, 5)],
                "prediction_origin_gps": GPS + k * WINDOW,
                "response_end_gps_exclusive": GPS + (k + 1) * WINDOW,
                "input_end_gps_exclusive": GPS + k * WINDOW,
                "input_windows": [k - i for i in range(1, 5)],
                "quality_selection": "All five windows: DATA bit and injection veto bits 0/1/2/4; no CW veto requirement",
            },
        )
        parts[split].append(row)
        lineage.append(anchor)
    return (
        parts,
        lineage,
        check_units(parts, {identity(recipe["scenario_id"], "group", g): g for g in groups}),
    )


def reconstruct_gwosc(recipe, source_root):
    if recipe["input_units"] != INPUT_UNITS or recipe["output_units"] != OUTPUT_UNITS:
        raise ValueError("GWOSC recipe units differ")
    (asset,) = [a for a in recipe["assets"] if a["role"] == "gwosc_hdf5"]
    arrays, inventory = native_arrays(contained(source_root, asset["path"]))
    summaries, windows = summarize(arrays["Strain"], arrays["DQmask"], arrays["Injmask"])
    parts, lineage, split = build_rows(recipe, summaries)
    used = sorted({k for row in lineage for k in [row["window_index"], *row["input_windows"]]})
    assignments = recipe["group_assignments"]
    cross_history = [
        {
            "window_index": row["window_index"],
            "split": row["split"],
            "input_window": k,
            "input_block_split": assignments.get(f"block{k // 32}"),
        }
        for row in lineage
        for k in row["input_windows"]
        if assignments.get(f"block{k // 32}") != row["split"]
    ]
    validation = {
        "native_inventory": inventory,
        "sample_count": len(arrays["Strain"]),
        "source_gps_start": GPS,
        "source_utc_start": "2024-01-05T17:33:34",
        "duration_seconds": DURATION,
        "sample_rate_hz": FS,
        "windows": windows,
        "eligible_windows": len(summaries),
        "eligible_forecasts": len(lineage),
        "used_windows": len(used),
        "quality_bit_names": DQ_NAMES,
        "injection_bit_names": INJ_NAMES,
        "all_source_quality_bit_counts": [
            int(np.count_nonzero(arrays["DQmask"] & (1 << b))) for b in range(9)
        ],
        "all_source_injection_bit_counts": [
            int(np.count_nonzero(arrays["Injmask"] & (1 << b))) for b in range(5)
        ],
        "mask_failure_counts": dict(
            Counter(reason for w in windows for reason in w["exclusion_reasons"])
        ),
        "welch": {
            "scale": 1e21,
            "fs_hz": FS,
            "window": "periodic Hann",
            "nperseg": 8192,
            "noverlap": 4096,
            "detrend": "constant mean per segment",
            "scaling": "density",
            "average": "mean",
            "one_sided": True,
            "frequency_spacing_hz": 0.5,
            "segments_per_window": 15,
            "band_bounds_inclusive_hz": BANDS,
            "integrator": "trapezoid",
            "output": "square root of integrated PSD",
        },
        "local_mean_detrend_fits": 15 * len(summaries),
        "discovery_rule_fits": 0,
        "cross_partition_observed_history": cross_history,
        "train_blocks": sorted(g for g, p in assignments.items() if p == "train"),
        "dev_blocks": sorted(g for g, p in assignments.items() if p == "dev"),
        "test_blocks": sorted(g for g, p in assignments.items() if p == "test"),
        "causal_input_ranges": all(
            max(stop for _, stop in a["input_slices"]) == a["response_slice"][0] for a in lineage
        ),
        "quality_scope": "Retrospective full-window availability/veto screening; not guaranteed all-category science-quality or injection-free strain",
        "independence_scope": "Adjacent blocks and overlapping observed history in one H1 interval; development is not guaranteed forward ordered",
        "response_scope": "Next-window noise-summary prediction with online measured history, not astrophysical source or detector-transfer evidence",
    }
    return (
        parts,
        lineage,
        {
            "split_check": split,
            "gwosc_validation": validation,
            "admission_blockers": [
                "CW injection veto not required; inspect the explicit source mask counts",
                "Single calibrated detector interval, shared history and retrospective quality selection limit independence",
                "Final scientific contract and source notice/rights review pending",
            ],
        },
    )
