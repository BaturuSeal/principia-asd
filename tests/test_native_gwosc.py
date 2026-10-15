from copy import deepcopy

import numpy as np
import pytest

from principia_asd.catalog.gwosc import (
    DQ_NAMES,
    DURATION,
    FS,
    GPS,
    INJ_NAMES,
    SAMPLES,
    build_rows,
    local_dataset,
    native_arrays,
    summarize,
)
from principia_asd.catalog.native import identity, runtime_binding

h5py = pytest.importorskip("h5py")


@pytest.fixture
def signal():
    t = np.arange(12 * SAMPLES) / FS
    # A 50 Hz tone has a known band RMS; a constant offset must disappear.
    return (
        (3 + np.sqrt(2) * np.sin(2 * np.pi * 50 * t)) * 1e-21,
        np.full(192, 511, dtype="u4"),
        np.full(192, 23, dtype="u4"),
    )


@pytest.fixture
def hdf(tmp_path):
    path = tmp_path / "source.h5"
    with h5py.File(path, "w") as f:
        for k, v in {
            "GPSstart": GPS,
            "Duration": DURATION,
            "Detector": "H1",
            "Observatory": "H",
            "Type": "StrainTimeSeries",
            "UTCstart": "2024-01-05T17:33:34",
            "FrameType": "H1_HOFT_C00_AR",
            "StrainChannel": "H1:GDS-CALIB_STRAIN_CLEAN_AR",
        }.items():
            f.create_dataset("meta/" + k, data=v)
        f.create_dataset("quality/simple/DQShortnames", data=DQ_NAMES)
        f.create_dataset("quality/injections/InjShortnames", data=INJ_NAMES)
        f.create_dataset("strain/GWOSCmeta", data="GWOSC-4KHZ_R1_STRAIN")
        for name, n, dtype, step, label, bits, fill in [
            ("strain/Strain", DURATION * FS, "f8", 1 / FS, "Strain", None, 0),
            ("quality/simple/DQmask", DURATION, "u4", 1.0, "DQmask", 9, 511),
            ("quality/injections/Injmask", DURATION, "u4", 1.0, "Injmask", 5, 23),
        ]:
            d = f.create_dataset(
                name,
                shape=(n,),
                dtype=dtype,
                chunks=(4096,),
                compression="gzip",
                compression_opts=1,
                fletcher32=True,
                fillvalue=fill,
            )
            d.attrs.update(
                Npoints=n,
                Xstart=GPS,
                Xspacing=step,
                Xunits="second",
                Xlabel="GPS time",
                Ylabel=label,
            )
            d.attrs.update({"Bits": bits} if bits else {"Yunits": ""})
    return path


def recipe():
    return {
        "scenario_id": "P100-003",
        "assets": [{"role": "gwosc_hdf5", "path": "raw/source.h5"}],
        "group_assignments": {
            f"block{k}": "train" if k < 4 else "dev" if k < 6 else "test" for k in range(8)
        },
    }


def summaries():
    return {k: [float(k + 1), float(k + 2), float(k + 3), float(k + 4)] for k in range(256)}


def test_known_tone_rms_offset_removal_and_no_cw_veto(signal):
    values, diag = summarize(*signal)
    assert len(values) == 12 and all(not d["exclusion_reasons"] for d in diag)
    assert all(abs(v[0] - 1) < 1e-12 for v in values.values())
    assert diag[0]["injection_bit_counts"] == [16, 16, 16, 0, 16]


@pytest.mark.parametrize("kind", ["data", "injection", "nonfinite"])
def test_masks_and_nonfinite_window_exclusions(signal, kind):
    strain, dq, inj = signal
    if kind == "data":
        dq[35] = 510
    elif kind == "injection":
        inj[35] = 22
    else:
        strain[2 * SAMPLES + 9] = np.nan
    result, diag = summarize(strain, dq, inj)
    assert 2 not in result and len(result) == 11
    assert diag[2]["exclusion_reasons"] == [
        {
            "data": "missing_DATA_flag",
            "injection": "required_injection_veto_unavailable",
            "nonfinite": "nonfinite_strain",
        }[kind]
    ]


def test_nonmandatory_quality_bits_are_disclosed_not_vetoed(signal):
    strain, dq, inj = signal
    dq[20] = 415
    result, diag = summarize(strain, dq, inj)
    assert len(result) == 12 and diag[1]["quality_bit_counts"][5:7] == [15, 15]


def test_future_waveform_does_not_change_earlier_summaries(signal):
    strain, dq, inj = signal
    before, _ = summarize(strain, dq, inj)
    strain[8 * SAMPLES :] *= 2
    after, _ = summarize(strain, dq, inj)
    assert all(before[k] == after[k] for k in range(8))
    assert after[8][0] == pytest.approx(before[8][0] * 2)


def test_exact_rows_causal_ranges_and_confirmation_custody():
    parts, lineage, check = build_rows(recipe(), summaries())
    assert {k: len(v) for k, v in parts.items()} == {"train": 124, "dev": 64, "test": 64}
    assert check["valid"]
    assert all("target" not in r for r in parts["test"])
    assert all(
        max(stop for _, stop in a["input_slices"]) == a["response_slice"][0] for a in lineage
    )
    r = next(
        r for r in parts["test"] if r["sample_id"] == identity("P100-003", "sample", "H1:w200")
    )
    assert r["lag1"] == 200 and r["lag4"] == 197 and r["median4"] == 198.5 and r["mad4"] == 1


def test_terminal_target_and_online_history_locality():
    before, lineage, _ = build_rows(recipe(), summaries())
    s = summaries()
    s[255][0] = 1e10
    after, _, _ = build_rows(recipe(), s)
    assert before == after
    s = summaries()
    s[200][0] = 1e9
    after, _, _ = build_rows(recipe(), s)
    old = {r["sample_id"]: r for rows in before.values() for r in rows}
    changed = {r["sample_id"] for rows in after.values() for r in rows if old[r["sample_id"]] != r}
    assert changed == {identity("P100-003", "sample", f"H1:w{k}") for k in range(201, 205)}
    assert all(a["response_end_gps_exclusive"] - a["prediction_origin_gps"] == 16 for a in lineage)


def test_full_five_window_eligibility_and_unchanged_boundary():
    s = summaries()
    del s[100]
    parts, _, _ = build_rows(recipe(), s)
    all_ids = {r["sample_id"] for rows in parts.values() for r in rows}
    assert all(identity("P100-003", "sample", f"H1:w{k}") not in all_ids for k in range(100, 105))
    r = recipe()
    r["group_assignments"]["block6"] = "dev"
    with pytest.raises(ValueError, match="confirmation"):
        build_rows(r, s)


def test_clock_shapes_and_resource_bounds(signal):
    strain, dq, inj = signal
    with pytest.raises(ValueError, match="sample clocks"):
        summarize(strain[:-1], dq, inj)
    with pytest.raises(ValueError, match="sample clocks"):
        summarize(strain, dq[:-1], inj)
    with pytest.raises(ValueError, match="sample clocks"):
        summarize(strain, dq.astype(float), inj)


def test_native_schema_filters_and_decoder_binding(hdf):
    arrays, inventory = native_arrays(hdf)
    assert arrays["Strain"].shape == (16777216,)
    assert inventory[0]["filters"] == [1, 3]
    assert all(arrays["Injmask"] == 23)
    env = runtime_binding("gwosc-native-causal-spectral-windows-v1")
    assert env["native_decoder"]["h5py"] == h5py.__version__
    assert "principia_asd.catalog.gwosc" in env["module_hashes"]


@pytest.mark.parametrize(
    "name,key,value",
    [
        ("strain/Strain", "Xspacing", 1 / 4000),
        ("strain/Strain", "Xstart", GPS + 1),
        ("strain/Strain", "Yunits", "meter"),
        ("quality/simple/DQmask", "Bits", 8),
    ],
)
def test_clock_and_unit_mutation_denied(hdf, name, key, value):
    with h5py.File(hdf, "a") as f:
        f[name].attrs[key] = value
    with pytest.raises(ValueError, match="clock, mask count or units"):
        native_arrays(hdf)


@pytest.mark.parametrize(
    "name,value",
    [
        ("meta/Detector", "L1"),
        ("meta/UTCstart", "2024-01-05T17:33:35"),
        (
            "quality/injections/InjShortnames",
            [
                "NO_CBC_HW_INJ",
                "NO_BURST_HW_INJ",
                "NO_DETCHAR_HW_INJ",
                "ALL_CW_CLEAR",
                "NO_STOCH_HW_INJ",
            ],
        ),
    ],
)
def test_source_identity_and_mask_meaning_mutations(hdf, name, value):
    with h5py.File(hdf, "a") as f:
        del f[name]
        f.create_dataset(name, data=value)
    with pytest.raises(ValueError, match="identity or mask semantics"):
        native_arrays(hdf)


@pytest.mark.parametrize(
    "kind", ["soft", "external", "external_group", "virtual", "filter", "object"]
)
def test_indirect_storage_and_unsupported_decoder_denied(hdf, kind, tmp_path):
    with h5py.File(hdf, "a") as f:
        if kind == "external_group":
            del f["strain"]
            f["strain"] = h5py.ExternalLink("missing.h5", "/strain")
        else:
            del f["strain/Strain"]
            if kind == "soft":
                f["strain/Strain"] = h5py.SoftLink("/missing")
            elif kind == "external":
                f["strain/Strain"] = h5py.ExternalLink("missing.h5", "/data")
            elif kind == "virtual":
                layout = h5py.VirtualLayout(shape=(DURATION * FS,), dtype="f8")
                layout[:] = h5py.VirtualSource(
                    str(tmp_path / "missing.h5"), "data", shape=layout.shape
                )
                f.create_virtual_dataset("strain/Strain", layout)
            elif kind == "filter":
                f.create_dataset(
                    "strain/Strain",
                    shape=(DURATION * FS,),
                    dtype="f8",
                    chunks=(4096,),
                    shuffle=True,
                )
            else:
                f.create_dataset("strain/Strain", data=["unexpected"])
    with pytest.raises(ValueError):
        native_arrays(hdf)


def test_declared_quality_bits_only(hdf):
    with h5py.File(hdf, "a") as f:
        f["quality/injections/Injmask"][0] = 64
    with pytest.raises(ValueError, match="Undeclared"):
        native_arrays(hdf)


def test_local_dataset_rejects_group_instead_of_measurement(hdf):
    with h5py.File(hdf, "r") as f:
        with pytest.raises(ValueError, match="invalid GWOSC dataset"):
            local_dataset(f, "strain")


def test_no_mutation_of_summaries_or_recipe():
    r, s = recipe(), summaries()
    copy = deepcopy((r, s))
    build_rows(r, s)
    assert (r, s) == copy
