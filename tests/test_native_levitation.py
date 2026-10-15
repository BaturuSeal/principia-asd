import io
import struct
import sys

import numpy as np
import pytest
from scipy.io import savemat

from principia_asd.catalog import levitation
from principia_asd.catalog.levitation import (
    archive_listing,
    bounded_command,
    decode_mat,
    raw_forecasts,
    reconstruct_levitation,
)
from principia_asd.catalog.native import identity


def mat(values, *, compressed=False):
    buffer = io.BytesIO()
    savemat(buffer, values, do_compression=compressed)
    return buffer.getvalue()


def signal(dt=0.0005, n=161, bias=0):
    t = np.arange(1, n + 1, dtype=float) * dt
    return t, np.sin(t * 120) + bias


def cohort(monkeypatch):
    contents, assignments, names = {"Data/ReadME.txt": b"n raw; de denoised"}, {}, []
    for i, split in enumerate(("train", "dev", "test")):
        name = f"Data/data{1142 + i}n.mat"
        names.append(name)
        t, y = signal(bias=i)
        contents[name] = mat({"t": t, "noisy_s": y})
        contents[name.removesuffix("n.mat") + "de.mat"] = mat({"t": t, "denoised_s": y / 2})
        assignments[f"data{1142 + i}n"] = split
    monkeypatch.setattr(levitation, "read_archive", lambda *_: contents)
    return contents, {
        "scenario_id": "P100-068",
        "assets": [{"role": "levitation_traces", "path": "raw.rar"}],
        "raw_members": names,
        "group_assignments": assignments,
        "decoder_binding": {},
    }


@pytest.mark.parametrize("dt", [0.0005, 0.001])
def test_native_clock_horizon_calibration_and_sample_coordinates(dt):
    t, y = signal(dt)
    a, b, actual_dt = decode_mat(mat({"t": t, "noisy_s": y}), "noisy_s")
    rows = list(raw_forecasts(a, b, actual_dt))
    index, values, target, coords = rows[0]
    assert t[coords["origin_index0"]] > 0.05
    assert t[index] - values["t"] == pytest.approx(0.005)
    assert coords["delay_indices0"] == [int(round(v / dt)) for v in (0.05, 0.045, 0.04, 0.035)]
    assert values["offset"] == np.mean(y[:20])
    assert target == y[index]
    for j, k in enumerate(coords["delay_indices0"]):
        assert values[f"y{j}"] == y[k] - values["offset"]


def test_complete_raw_denoised_cohort_identity_lineage_and_no_test_outputs(tmp_path, monkeypatch):
    _, recipe = cohort(monkeypatch)
    parts, lineage, checks = reconstruct_levitation(recipe, tmp_path)
    assert {p: len(rows) for p, rows in parts.items()} == {"train": 6, "dev": 6, "test": 6}
    assert checks["split_check"]["valid"]
    assert checks["levitation_validation"]["raw_samples"] == 483
    assert checks["levitation_validation"]["all_raw_denoised_clocks_equal"]
    assert all("target" not in r for r in parts["test"])
    assert lineage[0]["target_index0"] == 110
    assert lineage[0]["sample_id"] == identity("P100-068", "sample", "data1142n-index-110")
    assert checks["recordings"][0]["calibration_indices0"] == list(range(20))


def test_denoised_values_and_terminal_test_response_never_enter_inputs(tmp_path, monkeypatch):
    contents, recipe = cohort(monkeypatch)
    before = reconstruct_levitation(recipe, tmp_path)[0]
    t, y = signal(bias=2)
    y[-1] += 300
    contents["Data/data1144n.mat"] = mat({"t": t, "noisy_s": y})
    for i in range(3):
        contents[f"Data/data{1142 + i}de.mat"] = mat({"t": t, "denoised_s": y * 1000})
    assert reconstruct_levitation(recipe, tmp_path)[0] == before


def test_future_raw_values_do_not_rewrite_earlier_features():
    t, y = signal()
    before = list(raw_forecasts(t, y, 0.0005))
    y[110:] += 100
    after = list(raw_forecasts(t, y, 0.0005))
    assert before[0][1] == after[0][1]
    assert before[0][2] != after[0][2]
    assert before[1][1] != after[1][1]  # online history deliberately becomes observable


@pytest.mark.parametrize(
    "problem",
    [
        "nan",
        "duplicate",
        "irregular",
        "origin",
        "unsupported_dt",
        "complex",
        "unequal",
        "hidden",
        "matrix",
    ],
)
def test_invalid_native_vectors_fail_explicitly(problem):
    t, y = signal()
    values = {"t": t, "noisy_s": y}
    if problem == "nan":
        y[10] = np.nan
    elif problem == "duplicate":
        t[10] = t[9]
    elif problem == "irregular":
        t[10] += 0.00001
    elif problem == "origin":
        t += 0.0005
    elif problem == "unsupported_dt":
        t *= 3
    elif problem == "complex":
        values["noisy_s"] = y + 1j
    elif problem == "unequal":
        values["noisy_s"] = y[:-1]
    elif problem == "hidden":
        values["fitted_state"] = y
    elif problem == "matrix":
        values["noisy_s"] = np.zeros((20, 20))
    with pytest.raises(ValueError):
        decode_mat(mat(values), "noisy_s")


def test_mat_compression_truncation_and_oversized_allocation_rejected():
    t, y = signal()
    with pytest.raises(ValueError, match="Compressed"):
        decode_mat(mat({"t": t, "noisy_s": y}, compressed=True), "noisy_s")
    raw = mat({"t": t, "noisy_s": y})
    with pytest.raises(ValueError):
        decode_mat(raw[:-2], "noisy_s")
    bad = bytearray(raw)
    # First matrix dimensions: array flags (16 bytes), dimension tag (8 bytes).
    struct.pack_into("<ii", bad, 160, 1, 2_000_000_000)
    with pytest.raises(ValueError, match="allocation"):
        decode_mat(bytes(bad), "noisy_s")


def test_pair_clock_inventory_duplicate_trace_and_group_guards(tmp_path, monkeypatch):
    contents, recipe = cohort(monkeypatch)
    old = contents["Data/data1142de.mat"]
    t, y = signal(dt=0.001)
    contents["Data/data1142de.mat"] = mat({"t": t, "denoised_s": y})
    with pytest.raises(ValueError, match="pair clocks"):
        reconstruct_levitation(recipe, tmp_path)
    contents["Data/data1142de.mat"] = old
    contents["Data/unknown.mat"] = b"ignored?"
    with pytest.raises(ValueError, match="unregistered"):
        reconstruct_levitation(recipe, tmp_path)
    del contents["Data/unknown.mat"]
    contents["Data/data1143n.mat"] = contents["Data/data1142n.mat"]
    with pytest.raises(ValueError, match="Duplicated acquisition"):
        reconstruct_levitation(recipe, tmp_path)
    recipe["group_assignments"]["invented"] = "train"
    with pytest.raises(ValueError, match="assignments"):
        reconstruct_levitation(recipe, tmp_path)


def listing(name="Data/data1142n.mat", kind="-", size=16232):
    return f"{kind}rw-r--r--  0 0 0 {size} Jan 10 2024 {name}\n".encode()


@pytest.mark.parametrize(
    "raw",
    [
        listing("../escape"),
        listing("/Data/a"),
        listing(kind="l"),
        listing() + listing(),
        listing(size=100001),
        listing("Data/evil.py"),
        listing(kind="d"),
        listing("Data/data1142n.mat -> /private"),
    ],
)
def test_bounded_archive_inventory_rejects_unsafe_members(raw):
    with pytest.raises(ValueError):
        archive_listing(raw)


def test_archive_expanded_limit_and_frozen_decoder():
    assert archive_listing(listing())["Data/data1142n.mat"]["bytes"] == 16232
    with pytest.raises(ValueError, match="expanded"):
        archive_listing(listing(), max_bytes=10)


def test_archive_decoder_mutation_and_missing_capability(tmp_path, monkeypatch):
    monkeypatch.setattr(levitation, "decoder_binding", lambda: {"version": "new"})
    with pytest.raises(ValueError, match="differs"):
        levitation.read_archive(tmp_path / "missing", {"version": "frozen"})


def test_decoder_rejects_non_bsdtar(monkeypatch, tmp_path):
    monkeypatch.setattr(levitation.shutil, "which", lambda _: str(tmp_path / "tar"))
    monkeypatch.setattr(levitation, "bounded_command", lambda *a, **k: b"tar (GNU tar) 1.35")
    with pytest.raises(ValueError, match="requires bsdtar"):
        levitation.decoder_binding()


def test_bounded_command_output_stderr_failure_and_timeout():
    assert bounded_command([sys.executable, "-c", "print('ok')"], max_bytes=10) == b"ok\n"
    with pytest.raises(ValueError, match="output limit"):
        bounded_command([sys.executable, "-c", "print('x'*10000)"], max_bytes=10)
    with pytest.raises(ValueError, match="failed"):
        bounded_command([sys.executable, "-c", "import sys;sys.exit(1)"], max_bytes=10)
    with pytest.raises(ValueError, match="time limit"):
        bounded_command(
            [sys.executable, "-c", "import time;time.sleep(5)"], max_bytes=10, timeout=0.05
        )
