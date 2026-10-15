"""Bounded native LDV-voltage reconstruction; no filtering or fitted dynamics.

Raw and denoised files are paired for custody only. Predictions use raw voltage,
the initial twenty raw samples and past delays. Source Matlab is never executed.
"""

import hashlib
import io
import os
import re
import selectors
import shutil
import struct
import subprocess
import time
from pathlib import Path

import numpy as np
from scipy.io import loadmat, whosmat

from ..io import contained, file_sha
from .splits import check_units


def bounded_command(command, *, max_bytes, timeout=15):
    """Read pipes incrementally; kill on time/size limits, never extract to disk."""
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    with subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
    ) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, "stdout")
                selector.register(process.stderr, selectors.EVENT_READ, "stderr")
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ValueError("Archive decoder exceeded time limit")
                    for key, _ in selector.select(min(remaining, 0.1)):
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        output[key.data].extend(chunk)
                        limit = max_bytes if key.data == "stdout" else 8192
                        if len(output[key.data]) > limit:
                            raise ValueError("Archive decoder exceeded output limit")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("Archive decoder exceeded time limit")
                if process.wait(timeout=remaining) != 0 or output["stderr"]:
                    raise ValueError("Archive decoder failed or reported a warning")
        except BaseException:
            process.kill()
            process.wait()
            raise
    return bytes(output["stdout"])


def decoder_binding():
    executable = shutil.which("bsdtar") or shutil.which("tar")
    if not executable:
        raise ValueError("Native RAR preparation requires bsdtar/libarchive")
    executable = str(Path(executable).resolve())
    version = bounded_command([executable, "--version"], max_bytes=4096).decode("ascii").strip()
    if not version.startswith("bsdtar ") or "libarchive " not in version:
        raise ValueError("Native RAR preparation requires bsdtar/libarchive, not another tar")
    return {"executable": executable, "sha256": file_sha(Path(executable)), "version": version}


def archive_listing(raw, *, max_bytes=4_000_000, max_member_bytes=100_000):
    """Accept only this source's plain Data directory, MAT files and ReadME."""
    records = {}
    total = 0
    lines = raw.decode("ascii").splitlines()
    if not 1 <= len(lines) <= 128:
        raise ValueError("Invalid archive member count")
    for line in lines:
        match = re.fullmatch(
            r"([-d])[rwx-]{9}\s+\d+\s+\S+\s+\S+\s+(\d+)\s+"
            r"[A-Za-z]{3}\s+\d+\s+[0-9:]+\s+(Data(?:/(?:data[1-9][0-9]*(?:n|de)\.mat|ReadME\.txt))?/?)",
            line,
        )
        if not match:
            raise ValueError("Unsafe or unsupported archive member metadata")
        kind, size, name = match[1], int(match[2]), match[3].rstrip("/")
        if name in records or (name == "Data") != (kind == "d"):
            raise ValueError("Duplicate or invalid archive member type")
        if size > max_member_bytes or (kind == "d" and size):
            raise ValueError("Oversized archive member")
        total += size
        if total > max_bytes:
            raise ValueError("Archive expanded size exceeds limit")
        records[name] = {"bytes": size, "directory": kind == "d"}
    return records


def read_archive(path, expected_binding):
    binding = decoder_binding()
    if binding != expected_binding:
        raise ValueError("Archive decoder differs from the frozen preparation recipe")
    if path.stat().st_size > 2_000_000 or path.read_bytes()[:8] != b"Rar!\x1a\x07\x01\x00":
        raise ValueError("Unsupported or oversized RAR5 acquisition")
    listing = archive_listing(
        bounded_command([binding["executable"], "-tvf", str(path)], max_bytes=32_768)
    )
    members = {}
    for name, item in listing.items():
        if item["directory"]:
            continue
        raw = bounded_command(
            [binding["executable"], "-xOf", str(path), "--", name],
            max_bytes=item["bytes"],
        )
        if len(raw) != item["bytes"]:
            raise ValueError("Archive member length differs from its header")
        members[name] = raw
    return members


def decode_mat(raw, signal_name):
    """Preflight uncompressed MATLAB 5 numeric vectors before allocating arrays."""
    if signal_name not in {"noisy_s", "denoised_s"}:
        raise ValueError("Unregistered signal variable")
    if len(raw) > 100_000 or len(raw) < 136 or raw[124:128] != b"\x00\x01IM":
        raise ValueError("Unsupported MATLAB encoding or size")
    # This release contains plain little-endian matrices. Compressed streams,
    # sparse/object/class data and extra hidden arrays are not accepted.
    position, count = 128, 0
    while position < len(raw):
        if position + 8 > len(raw):
            raise ValueError("Truncated MATLAB matrix tag")
        kind, size = struct.unpack_from("<II", raw, position)
        if kind != 14 or size < 32 or position + 8 + size > len(raw):
            raise ValueError("Compressed, unsupported or truncated MATLAB matrix")
        position += 8 + ((size + 7) // 8) * 8
        count += 1
    if position != len(raw) or count != 2:
        raise ValueError("Unexpected MATLAB matrix inventory")
    inventory = whosmat(io.BytesIO(raw))
    if len(inventory) != 2 or {item[0] for item in inventory} != {"t", signal_name}:
        raise ValueError("Missing, duplicated or hidden MATLAB variable")
    for _, shape, kind in inventory:
        if kind != "double" or len(shape) != 2 or min(shape) != 1 or not 120 <= max(shape) <= 5000:
            raise ValueError("Unexpected signal shape, numeric type or allocation")
    values = loadmat(io.BytesIO(raw), variable_names=["t", signal_name])
    t, y = values["t"], values[signal_name]
    if not np.isrealobj(t) or not np.isrealobj(y):
        raise ValueError("Complex acquisition values are unsupported")
    t, y = t.ravel(), y.ravel()
    if len(t) != len(y) or not np.isfinite(t).all() or not np.isfinite(y).all():
        raise ValueError("Nonfinite or unequal acquisition vectors")
    delta = np.diff(t)
    dt = float(np.median(delta))
    if not any(np.isclose(dt, value, rtol=0, atol=1e-12) for value in (0.0005, 0.001)):
        raise ValueError("Unsupported acquisition interval")
    if not np.allclose(delta, dt, rtol=0, atol=1e-12) or not np.isclose(
        t[0], dt, rtol=0, atol=1e-12
    ):
        raise ValueError("Irregular, duplicate or shifted acquisition clock")
    return t, y, dt


def raw_forecasts(t, y, dt):
    """Expand causal sample coordinates; no future filtering or interpolation."""
    lag = int(round(0.005 / dt))
    start = int(round(0.05 / dt))
    offset = float(np.mean(y[:20]))
    for k in range(start, len(y) - lag, lag):
        indices = [k, k - lag, k - 2 * lag, k - 3 * lag]
        target = k + lag
        if min(indices) < 20 or target >= len(t):
            raise ValueError("Calibration overlaps history or forecast lies outside acquisition")
        if not np.allclose(t[k] - t[indices], [0, 0.005, 0.01, 0.015], rtol=0, atol=1e-12):
            raise ValueError("Stored history is not the declared causal delay window")
        if not np.isclose(t[target] - t[k], 0.005, rtol=0, atol=1e-12):
            raise ValueError("Stored forecast horizon differs from five milliseconds")
        values = {f"y{j}": float(y[index] - offset) for j, index in enumerate(indices)}
        yield (
            target,
            {**values, "offset": offset, "t": float(t[k])},
            float(y[target]),
            {"origin_index0": k, "delay_indices0": indices, "target_index0": target},
        )


def reconstruct_levitation(recipe, source_root):
    from .native import _registered_groups, _row, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "levitation_traces"]
    members = read_archive(contained(source_root, asset["path"]), recipe["decoder_binding"])
    raw_names = recipe["raw_members"]
    if (
        not raw_names
        or len(raw_names) != len(set(raw_names))
        or any(not re.fullmatch(r"Data/data[1-9][0-9]*n\.mat", name) for name in raw_names)
    ):
        raise ValueError("Invalid raw trace inventory")
    paired = {name: name.removesuffix("n.mat") + "de.mat" for name in raw_names}
    if set(members) != {*raw_names, *paired.values(), "Data/ReadME.txt"}:
        raise ValueError("Missing or unregistered raw/denoised pair or source documentation")
    groups = {Path(name).stem for name in raw_names}
    assignments = _registered_groups(recipe, groups)
    parts, lineage, traces, units, signals = (
        {p: [] for p in ("train", "dev", "test")},
        [],
        [],
        {},
        {},
    )
    for name in raw_names:
        t, y, dt = decode_mat(members[name], "noisy_s")
        other_t, _, _ = decode_mat(members[paired[name]], "denoised_s")
        if not np.array_equal(t, other_t):
            raise ValueError("Raw/denoised acquisition pair clocks differ")
        group = Path(name).stem
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        fingerprint = hashlib.sha256(y.astype("<f8").tobytes()).hexdigest()
        if fingerprint in signals:
            raise ValueError("Duplicated acquisition signal with distinct trace identities")
        signals[fingerprint] = group
        count = 0
        for index, values, target, coordinates in raw_forecasts(t, y, dt):
            row, source = _row(
                recipe["scenario_id"],
                group + f"-index-{index}",
                group,
                split,
                values,
                target,
                {"member": name, "variable": "noisy_s", **coordinates},
            )
            parts[split].append(row)
            lineage.append(source)
            count += 1
        if not count:
            raise ValueError("Acquisition has no eligible declared forecast window")
        traces.append(
            {
                "member": name,
                "sha256": hashlib.sha256(members[name]).hexdigest(),
                "paired_denoised_member": paired[name],
                "paired_denoised_sha256": hashlib.sha256(members[paired[name]]).hexdigest(),
                "group": identity(recipe["scenario_id"], "group", group),
                "split": split,
                "source_samples": len(t),
                "timestamp_start_s": float(t[0]),
                "timestamp_end_s": float(t[-1]),
                "sample_interval_s": dt,
                "calibration_indices0": list(range(20)),
                "calibration_last_time_s": float(t[19]),
                "eligible_rows": count,
                "signal_fingerprint": fingerprint,
            }
        )
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "levitation_validation": {
                "raw_traces": len(traces),
                "linked_denoised_traces": len(traces),
                "raw_samples": sum(record["source_samples"] for record in traces),
                "eligible_rows": sum(record["eligible_rows"] for record in traces),
                "sample_intervals_s": sorted(
                    {round(record["sample_interval_s"], 12) for record in traces}
                ),
                "distinct_raw_signals": len(signals),
                "forecast_horizon_s": 0.005,
                "maximum_history_s": 0.015,
                "initial_calibration_samples": 20,
                "nonfinite_or_failed_windows_dropped": 0,
                "denoised_values_used_as_inputs": False,
                "future_filtering_or_fitting": False,
                "all_raw_denoised_clocks_equal": True,
            },
            "source_archive": asset["path"],
            "source_readme_sha256": hashlib.sha256(members["Data/ReadME.txt"]).hexdigest(),
            "decoder_binding": recipe["decoder_binding"],
            "recordings": traces,
            "independence_scope": "Trace-level partition only; all traces share a levitator/object setup. Separate acquisition files do not establish independent devices or excitation regimes.",
            "response_scope": "Raw LDV voltage at a five-millisecond horizon, conditioned on permitted online raw delays and initial calibration; no identified mechanics or free-running dynamics claim.",
            "admission_blockers": [
                "Final scientific-contract and source-rights/notice review remain pending",
                "Excitation metadata and independent installation replication are not established by trace identifiers",
                "Sensor calibration, latency and measurement-error perturbation model require scientific review",
            ],
        },
    )
