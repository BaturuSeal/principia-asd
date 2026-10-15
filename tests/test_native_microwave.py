import json
import sys

import numpy as np
import pytest

from principia_asd.catalog.microwave import (
    GROUP,
    INPUT_UNITS,
    PARSER,
    SPECS,
    decoder,
    decoder_binding,
    native_arrays,
    original_assignments,
    reconstruct_microwave,
)
from principia_asd.catalog.native import prepare, reconstruct, runtime_binding
from principia_asd.io import file_sha, write_json

h5py = pytest.importorskip("h5py")


def source_values():
    u = np.arange(51 * 13 * 13, dtype=float).reshape(1, 51, 1, 1, 1, 13, 13) / 10000 + 1j
    return {
        "USB": u,
        "amp fc pumps": np.r_[0.0, np.linspace(0.13, 0.18, 50)],
        "freq sig": (4_199_400_000.0 + 100_000 * np.arange(13))[None, :],
        "freq fc pumps": (100_000.0 * np.arange(1, 13))[None, :],
        "freq param pumps": np.empty((1, 0)),
        "amp param pumps": np.array([1.0]),
        "phase fc pumps": np.array([0.0]),
        "phase param pumps": np.array([0.0]),
        "df": np.array([100_000.0]),
        "pumping scheme": np.array(13, dtype="i8"),
    }


def make_source(tmp_path, values=None):
    values = source_values() if values is None else values
    path = tmp_path / "source.h5"
    with h5py.File(path, "w") as h:
        g = h.create_group(GROUP)
        for name, a in values.items():
            d = g.create_dataset(name, data=a)
            d.attrs["Unit"] = SPECS[name][3]
        g.create_dataset("USB std", data=np.full((51, 13, 13), np.nan))
        h.create_dataset("ignored_fitted_state", data=np.full(12, np.nan))
    return path


def make_recipe(tmp_path, values=None):
    p = make_source(tmp_path, values)
    meta = tmp_path / "metadata.json"
    meta.write_text(
        json.dumps(
            {
                "id": 18938314,
                "doi": "10.5281/zenodo.18938314",
                "metadata": {"version": "1.0", "license": {"id": "cc-by-4.0"}},
            }
        )
    )
    text = tmp_path / "Readme.txt"
    text.write_text("'2025-11-21_16_40_49' -- Dataset to create Fig.4")
    return {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-028",
        "parser": PARSER,
        "input_units": INPUT_UNITS.copy(),
        "output_units": "fsu; instrument full-scale units",
        "group_assignments": original_assignments("P100-028"),
        "assets": [
            {"path": f.name, "role": role, "bytes": f.stat().st_size, "sha256": file_sha(f)}
            for f, role in [
                (p, "microwave_hdf5"),
                (meta, "source_metadata"),
                (text, "source_readme"),
            ]
        ],
    }


def test_full_cohort_direction_and_calibration_custody(tmp_path):
    r = make_recipe(tmp_path)
    parts, lineage, checks = reconstruct(r, tmp_path)
    assert {k: len(v) for k, v in parts.items()} == {"train": 3744, "dev": 780, "test": 1560}
    assert checks["split_check"]["valid"] and len(lineage) == 6084
    v = checks["microwave_validation"]
    assert v["group_counts"] == {"train": 24, "dev": 5, "test": 10}
    assert v["native_complex_values"] == 8619 and v["calibration_complex_values"] == 468
    assert all("target" not in x for x in parts["test"])
    assert len({x["sample_id"] for rows in parts.values() for x in rows}) == 6084
    first = lineage[0]
    assert first["native_zero_based_index"] == [0, 12, 0, 0, 0, 0, 1]
    assert first["calibration_pump_indices"] == [0, 1, 11]
    sample = next(
        x for rows in parts.values() for x in rows if x["sample_id"] == first["sample_id"]
    )
    u = source_values()["USB"][0, :, 0, 0, 0]
    assert sample["lo"] == abs(u[1, 0, 1]) and sample["hi"] == abs(u[11, 0, 1])
    assert sample["noise"] == abs(u[0, 0, 1]) and sample["target"] == abs(u[12, 0, 1])
    assert sample["sep"] == 1 and sample["lo"] != abs(u[1, 1, 0])


@pytest.mark.parametrize(
    "field,value",
    [
        ("amp fc pumps", np.zeros(51)),
        ("freq sig", np.zeros((1, 13))),
        ("freq fc pumps", np.zeros((1, 12))),
        ("phase fc pumps", np.array([1.0])),
        ("amp param pumps", np.array([0.0])),
        ("df", np.array([1.0])),
        ("pumping scheme", np.array(3)),
    ],
)
def test_control_and_frequency_identity(tmp_path, field, value):
    a = source_values()
    a[field] = value
    p = make_source(tmp_path, a)
    with pytest.raises(ValueError):
        native_arrays(p)


@pytest.mark.parametrize(
    "mutation",
    ["nan", "shape", "real_dtype", "unit", "filtered", "virtual", "external", "soft", "huge"],
)
def test_hdf5_decoding_guards(tmp_path, mutation):
    p = make_source(tmp_path)
    with h5py.File(p, "r+") as h:
        g = h[GROUP]
        if mutation == "nan":
            g["USB"][0, 50, 0, 0, 0, 0, 1] = complex(np.nan, 0)
        elif mutation == "unit":
            g["USB"].attrs["Unit"] = "W"
        else:
            del g["USB"]
            if mutation == "external":
                g["USB"] = h5py.ExternalLink("missing-canary.h5", "/secret")
            elif mutation == "soft":
                g["USB"] = h5py.SoftLink("/missing-canary")
            elif mutation == "virtual":
                layout = h5py.VirtualLayout(shape=SPECS["USB"][0], dtype="c16")
                layout[:] = h5py.VirtualSource("missing-canary.h5", "secret", shape=SPECS["USB"][0])
                g.create_virtual_dataset("USB", layout).attrs["Unit"] = "fsu complex"
            else:
                shape = (
                    (51, 13, 13)
                    if mutation == "shape"
                    else (10**9,)
                    if mutation == "huge"
                    else SPECS["USB"][0]
                )
                d = g.create_dataset(
                    "USB",
                    shape=shape,
                    dtype="f8" if mutation == "real_dtype" else "c16",
                    compression="gzip" if mutation in {"filtered", "huge"} else None,
                )
                d.attrs["Unit"] = "fsu complex"
    with pytest.raises(ValueError):
        native_arrays(p)


def test_external_raw_storage_denied(tmp_path):
    p = make_source(tmp_path)
    with h5py.File(p, "r+") as h:
        g = h[GROUP]
        del g["USB"]
        d = g.create_dataset(
            "USB",
            shape=SPECS["USB"][0],
            dtype="c16",
            external=[("missing.bin", 0, h5py.h5f.UNLIMITED)],
        )
        d.attrs["Unit"] = "fsu complex"
    with pytest.raises(ValueError, match="storage"):
        native_arrays(p)


def test_indirect_group_denied_before_following(tmp_path):
    p = tmp_path / "indirect.h5"
    with h5py.File(p, "w") as h:
        h["Scattering"] = h5py.ExternalLink("missing-canary.h5", "/secret")
    with pytest.raises(ValueError, match="group"):
        native_arrays(p)


def test_targets_never_change_inputs_and_unselected_values_unused(tmp_path):
    r = make_recipe(tmp_path)
    before = reconstruct_microwave(r, tmp_path)[0]
    with h5py.File(tmp_path / "source.h5", "r+") as h:
        d = h[GROUP + "/USB"]
        a = d[()]
        a[:, 41:] *= 5
        a[:, 2:11] *= 9
        for i in range(13):
            a[..., i, i] *= 10
        d[...] = a
    after = reconstruct_microwave(r, tmp_path)[0]
    assert before == after


def test_development_response_changes_only_its_response(tmp_path):
    r = make_recipe(tmp_path)
    before = reconstruct_microwave(r, tmp_path)[0]
    with h5py.File(tmp_path / "source.h5", "r+") as h:
        h[GROUP + "/USB"][0, 12, 0, 0, 0, 0, 1] *= 2
    after = reconstruct_microwave(r, tmp_path)[0]
    changed = [
        (a, b)
        for split in before
        for a, b in zip(before[split], after[split], strict=True)
        if a != b
    ]
    assert len(changed) == 1
    a, b = changed[0]
    assert b["target"] == 2 * a["target"]
    assert {k: v for k, v in a.items() if k != "target"} == {
        k: v for k, v in b.items() if k != "target"
    }


def test_calibration_is_pair_local(tmp_path):
    r = make_recipe(tmp_path)
    before = reconstruct_microwave(r, tmp_path)[0]
    with h5py.File(tmp_path / "source.h5", "r+") as h:
        h[GROUP + "/USB"][0, 11, 0, 0, 0, 0, 1] *= 2
    after = reconstruct_microwave(r, tmp_path)[0]
    changed = [
        (a, b)
        for split in before
        for a, b in zip(before[split], after[split], strict=True)
        if a != b
    ]
    assert len(changed) == 39
    assert all(
        b["hi"] == 2 * a["hi"]
        and {k: v for k, v in a.items() if k != "hi"} == {k: v for k, v in b.items() if k != "hi"}
        for a, b in changed
    )


def test_source_hash_mutation_denied(tmp_path):
    r = make_recipe(tmp_path)
    with h5py.File(tmp_path / "source.h5", "r+") as h:
        h[GROUP + "/USB"][0, 12, 0, 0, 0, 0, 1] = 99
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(r, tmp_path)


@pytest.mark.parametrize("change", ["units", "groups", "metadata"])
def test_recipe_identity_guards(tmp_path, change):
    r = make_recipe(tmp_path)
    if change == "units":
        r["input_units"]["g"] = "watts"
    elif change == "groups":
        r["group_assignments"]["pump-41"] = "train"
    else:
        p = tmp_path / "metadata.json"
        d = json.loads(p.read_text())
        d["metadata"]["version"] = "2"
        p.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        reconstruct_microwave(r, tmp_path)


def test_optional_decoder_error_is_explicit(monkeypatch):
    monkeypatch.setitem(sys.modules, "h5py", None)
    with pytest.raises(RuntimeError, match="separate curator environment"):
        decoder()
    assert "native_decoder" not in runtime_binding()


def test_decoder_bound_and_mutation_blocks_replay(tmp_path):
    r = make_recipe(tmp_path)
    rp = tmp_path / "recipe.json"
    write_json(rp, r)
    # Output outside source root, using sibling directories in the fixture's parent.
    source = tmp_path / "sources"
    source.mkdir()
    for a in r["assets"]:
        (tmp_path / a["path"]).rename(source / a["path"])
    out = tmp_path / "output"
    prepare(rp, source, out)
    env = json.loads((out / "preprocessing/environment.json").read_text())
    assert env["native_decoder"] == decoder_binding()
    env["native_decoder"]["hdf5"] = "changed"
    bad = tmp_path / "bad.json"
    write_json(bad, env)
    with pytest.raises(ValueError, match="runtime differs"):
        prepare(rp, source, tmp_path / "replay", expected_environment=bad)
    assert not (tmp_path / "replay").exists()
