"""Curator-only BUT-PPG v2 native signal features, with explicit layout caveats.

ECG/quality annotations never enter predictors. All participants and recording
conditions are retained. The 48 single-frame source encodings are disclosed,
not silently relabeled as ordinary three-channel WFDB time series.
"""

import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from pathlib import PurePosixPath

import numpy as np
from scipy.signal import detrend, find_peaks, periodogram

from ..io import contained, sha
from .fracture import bounded_zip
from .splits import check_units

PREFIX = "brno-university-of-technology-smartphone-ppg-database-but-ppg-2.0.0/"
SOURCE_URL = "https://www.physionet.org/content/butppg/2.0.0/"
META_HEADER = [
    "ID",
    "Gender",
    "Age [years]",
    "Height [cm]",
    "Weight [kg]",
    "Ear/finger",
    "Motion",
    "Blood pressure [mmHg]",
    "Glycaemia [mmol/l]",
    "SpO2 [%]",
]
INPUT_UNITS = {
    **dict.fromkeys(["acf_bpm", "agreement", "fft_bpm", "half_bpm"], "bpm"),
    **dict.fromkeys(["ear", "half_strength", "motion", "spectral_quality"], "dimensionless"),
}


def table(payload, headers):
    if len(payload) > 1_000_000:
        raise ValueError("Oversized PPG annotation table")
    rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig")), strict=True))
    if not rows or rows[0] != headers or not 1 <= len(rows) - 1 <= 4000:
        raise ValueError("Unexpected PPG annotation schema or count")
    result = {}
    for line, row in enumerate(rows[1:], 2):
        if (
            len(row) != len(headers)
            or not re.fullmatch(r"1[0-4][0-9][0-9]{3}", row[0])
            or row[0] in result
        ):
            raise ValueError("Invalid or duplicate PPG annotation identity")
        result[row[0]] = (dict(zip(headers, row, strict=True)), line)
    return result


def decode_ppg(header, payload, sid):
    """Decode only pinned int16 layouts and explicit source gains/baselines."""
    if len(header) > 50_000 or len(payload) > 1800:
        raise ValueError("Oversized PPG waveform")
    lines = [
        x.split()
        for x in header.decode("ascii").splitlines()
        if x.strip() and not x.startswith("#")
    ]
    if not lines or len(lines[0]) != 4 or lines[0][0] != sid + "_PPG":
        raise ValueError("Invalid PPG record identity")
    try:
        channels, fs, frames = int(lines[0][1]), float(lines[0][2]), int(lines[0][3])
    except ValueError as exc:
        raise ValueError("Invalid PPG header dimensions") from exc
    if (
        fs != 30
        or (channels, frames) not in {(300, 1), (3, 300)}
        or len(lines) != channels + 1
        or len(payload) != 2 * channels * frames
    ):
        raise ValueError("Unsupported PPG rate, layout or byte count")
    gains, baselines, names = [], [], []
    for fields in lines[1:]:
        if len(fields) not in {8, 9} or fields[0] != sid + "_PPG.dat" or fields[1] != "16":
            raise ValueError("Unsupported PPG signal file or encoding")
        match = re.fullmatch(r"([^()]+)\(([^()]+)\)/a\.u\.", fields[2])
        if not match:
            raise ValueError("Missing explicit PPG gain, baseline or units")
        gain, baseline = float(match[1]), float(match[2])
        if not math.isfinite(gain) or not math.isfinite(baseline) or gain == 0:
            raise ValueError("Invalid PPG calibration")
        if (
            fields[3:5] != ["0", "0"]
            or fields[7] != "0"
            or any(not re.fullmatch(r"-?[0-9]+", v) for v in fields[5:7])
        ):
            raise ValueError("Unsupported PPG ADC/storage declaration")
        gains.append(gain)
        baselines.append(baseline)
        names.append(fields[8] if len(fields) == 9 else "")
    raw = np.frombuffer(payload, dtype="<i2").astype(float)
    if np.any(raw == -32768):
        raise ValueError("Missing WFDB sample sentinel; no implicit imputation")
    if frames == 1:
        if any(names):
            raise ValueError("Unexpected names in single-frame source encoding")
        signal = (raw - np.asarray(baselines)) / np.asarray(gains)
        layout = "300_channels_one_frame_flattened_in_source_order"
        selected = "all 300 source scalar channels; historical temporal interpretation"
    else:
        if set(names) != {"PPG_R", "PPG_G", "PPG_B"} or len(set(names)) != 3:
            raise ValueError("Missing or duplicate PPG colour channel")
        signal = ((raw.reshape(frames, channels) - np.asarray(baselines)) / np.asarray(gains))[
            :, names.index("PPG_R")
        ]
        layout, selected = "three_channels_300_frames", "PPG_R"
    if not np.isfinite(signal).all() or np.std(signal) == 0:
        raise ValueError("Nonfinite or constant PPG segment")
    return signal, {
        "layout": layout,
        "selected_channel": selected,
        "header_channels": channels,
        "header_frames": frames,
        "interpreted_samples": len(signal),
        "sample_rate_hz": fs,
        "interpreted_duration_s": len(signal) / fs,
        "gain_baseline_sha256": sha({"gain": gains, "baseline": baselines}),
        "raw_missing_samples": 0,
    }


def signal_features(signal, fs=30):
    if (
        np.shape(signal) != (300,)
        or fs != 30
        or not np.isfinite(signal).all()
        or np.std(signal) == 0
    ):
        raise ValueError("Invalid ten-second PPG feature window")
    x = detrend(signal, type="linear")
    x = x / (np.std(x) + 1e-15)
    freq, power = periodogram(x, fs=fs, window="hann", nfft=4096, detrend=False)
    band = (freq >= 0.5) & (freq <= 4)
    ff, pp = freq[band], power[band]
    peak = float(ff[np.argmax(pp)])
    half = peak / 2 if peak >= 1 else peak
    near = np.abs(ff - half) < 0.1
    half_strength = float(pp[near].max() / max(pp.max(), 1e-15)) if near.any() else 0
    quality = float(pp[np.abs(ff - peak) < 0.12].sum() / max(pp.sum(), 1e-15))
    ac = np.correlate(x, x, mode="full")[len(x) - 1 :]
    lags = np.arange(max(1, int(fs / 4)), min(len(x) - 1, int(fs / 0.5)) + 1)
    peaks = find_peaks(ac[lags])[0]
    acf = float(fs / lags[peaks[np.argmax(ac[lags[peaks]])]]) if len(peaks) else peak
    return {
        "fft_bpm": 60 * peak,
        "acf_bpm": 60 * acf,
        "half_bpm": 60 * half,
        "half_strength": half_strength,
        "spectral_quality": quality,
        "agreement": abs(60 * (peak - acf)),
    }


def original_assignments(case, groups):
    from .native import identity

    held = set(
        sorted(groups, key=lambda g: hashlib.sha256(("P100-033:" + g).encode()).hexdigest())[:10]
    )
    available = set(groups) - held
    dev = set(
        sorted(available, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)]))[:8]
    )
    return {g: "test" if g in held else "dev" if g in dev else "train" for g in groups}


def archive_records(path):
    """Yield source-bound signals and neutral provenance, never ECG waveforms."""
    with bounded_zip(
        path, max_bytes=220_000_000, max_member_bytes=3_000_000, max_members=28_000
    ) as z:
        members = set(z.namelist())
        if any(not n.startswith(PREFIX) for n in members):
            raise ValueError("Unexpected PPG archive root")
        checksum_data = z.read(PREFIX + "SHA256SUMS.txt")
        hashes = {}
        for line in checksum_data.decode("ascii").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64}) (.+)", line)
            if not match or match[2] in hashes:
                raise ValueError("Invalid PPG publisher checksum inventory")
            hashes[match[2]] = match[1]
        if {PREFIX + n for n in hashes} != members - {PREFIX + "SHA256SUMS.txt"}:
            raise ValueError("Incomplete PPG publisher checksum inventory")

        def read(name):
            payload = z.read(PREFIX + name)
            if hashlib.sha256(payload).hexdigest() != hashes.get(name):
                raise ValueError("PPG member differs from publisher checksum")
            return payload

        ann = table(read("quality-hr-ann.csv"), ["ID", "Quality", "HR"])
        meta = table(read("subject-info.csv"), META_HEADER)
        headers = {
            PurePosixPath(n).name.removesuffix("_PPG.hea"): n
            for n in members
            if n.endswith("_PPG.hea")
        }
        records = read("RECORDS.txt").decode("ascii").splitlines()
        if len(records) != len(set(records)) or set(ann) != set(meta) or set(ann) != set(headers):
            raise ValueError("PPG annotation, metadata and record inventory differ")
        if {PREFIX + n + ".hea" for n in records} != {n for n in members if n.endswith(".hea")}:
            raise ValueError("PPG RECORDS inventory differs from archive")
        demographics = {}
        for sid, (md, _) in meta.items():
            profile = (md["Gender"], md["Age [years]"])
            if profile[0] not in {"F", "M"} or not re.fullmatch(r"[0-9]{2}", profile[1]):
                raise ValueError("Invalid participant identity metadata")
            if demographics.setdefault(sid[:3], profile) != profile:
                raise ValueError("Conflicting person-level PPG identity metadata")
        for sid, (a, ann_line) in ann.items():
            md, md_line = meta[sid]
            if (
                a["Quality"] not in {"0", "1"}
                or md["Ear/finger"] not in {"0", "1"}
                or md["Motion"] not in {"0", "1", "2", "3", "4", "5", "6", "7", "2;3"}
            ):
                raise ValueError("Unknown PPG quality or acquisition code")
            hr = float(a["HR"])
            if not math.isfinite(hr) or hr <= 0:
                raise ValueError("Missing ECG reference; no eligibility shrinkage")
            stem = sid + "/" + sid + "_PPG"
            if headers[sid] != PREFIX + stem + ".hea":
                raise ValueError("Ambiguous PPG signal identity")
            signal, native = decode_ppg(read(stem + ".hea"), read(stem + ".dat"), sid)
            yield (
                sid,
                hr,
                signal,
                {
                    **native,
                    "annotation_row": ann_line,
                    "metadata_row": md_line,
                    "header_member": PREFIX + stem + ".hea",
                    "data_member": PREFIX + stem + ".dat",
                    "header_sha256": hashes[stem + ".hea"],
                    "data_sha256": hashes[stem + ".dat"],
                    "source_quality": int(a["Quality"]),
                    "motion_code": md["Motion"],
                    "ear_code": int(md["Ear/finger"]),
                },
            )


def reconstruct_ppg(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "ppg_archive"]
    (meta,) = [a for a in recipe["assets"] if a["role"] == "source_metadata"]
    metadata = json.loads(
        contained(source_root, meta["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if (
        metadata["source_url"] != SOURCE_URL
        or metadata["source_version"] != "2.0.0; 2024-08-23"
        or metadata["license_or_terms"] != "CC BY 4.0"
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "bpm"
    ):
        raise ValueError("PPG source version, license or units differ")
    groups = [str(g) for g in range(100, 150)]
    case = recipe["scenario_id"]
    assignments = _registered_groups(recipe, groups)
    if assignments != original_assignments(case, groups):
        raise ValueError("Historical whole-person allocation changed")
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    layouts, quality, subjects, condition = Counter(), Counter(), Counter(), Counter()
    for sid, hr, signal, native in archive_records(contained(source_root, asset["path"])):
        group = sid[:3]
        split = assignments[group]
        units[identity(case, "group", group)] = group
        features = signal_features(signal)
        features.update(motion=int(native["motion_code"] != "0"), ear=native["ear_code"])
        anchor = {
            "source": asset["path"],
            **{
                k: v
                for k, v in native.items()
                if k not in {"source_quality", "motion_code", "ear_code"}
            },
        }
        row, trace = _row(case, sid, group, split, features, hr, anchor)
        parts[split].append(row)
        lineage.append(trace)
        layouts[native["layout"]] += 1
        quality[str(native["source_quality"])] += 1
        subjects[group] += 1
        condition[native["motion_code"]] += 1
    if set(subjects) != set(groups) or len(lineage) != 3888:
        raise ValueError("Incomplete PPG participant or sample cohort")
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "ppg_validation": {
                "source_recordings": len(lineage),
                "interpreted_signal_samples": len(lineage) * 300,
                "source_layout_counts": dict(layouts),
                "source_quality_counts": dict(quality),
                "source_motion_counts": dict(condition),
                "participant_recording_counts": dict(subjects),
                "group_counts": dict(Counter(assignments.values())),
                "fit_count": 0,
                "fitting_scope": "Zero rule/across-subject fits; separate within-segment detrending and scaling counted below",
                "linear_detrend_fits": len(lineage),
                "detrend_parameters_per_segment": 2,
                "signal_scale_estimates": len(lineage),
                "learned_across_subject_transforms": [],
                "ecg_waveforms_read": False,
                "human_quality_used_as_predictor": False,
                "acquisition_dates": "August 2020–December 2021 per registered source profile; release 2024-08-23",
                "scope": "Retrospective simultaneous ECG-reference estimation after complete source PPG segment, not future or clinical prediction",
            },
            "admission_blockers": [
                "48 source headers declare 300 channels and one frame; historical flattening requires temporal-orientation review before admission",
                "Source authors extracted, synchronized and segmented signals; raw smartphone video is not reconstructed",
                "Source-reference/quality annotation protocol, acquisition-condition availability, device transfer and rights/notices require review",
                "Rule complexity excludes signal decoding, per-segment detrending/scaling and spectral/autocorrelation feature computation; sensitivity is diagnostic",
            ],
        },
    )
