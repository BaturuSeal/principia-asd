from copy import deepcopy

import numpy as np
import pytest

from principia_asd.catalog.coral import (
    INPUT_UNITS,
    OFFSETS,
    PARSER,
    ROOT_IDENTITY,
    VARIABLE,
    build_rows,
    confirmation,
    local_dataset,
    native_arrays,
    reconstruct_coral,
    sample_map,
)
from principia_asd.catalog.native import identity, runtime_binding

h5py = pytest.importorskip("h5py")


@pytest.fixture
def grid():
    yy, xx = np.indices((360, 720))
    return (
        (yy + 2 * xx - 1000).astype("i2"),
        np.zeros((360, 720), "u1"),
        np.linspace(59.975, -59.975, 360).astype("f4"),
        np.linspace(-179.975, 179.975, 720).astype("f4"),
    )


def make_recipe(records):
    groups = sorted({r["group"] for r in records})
    assignments = {g: "test" if confirmation(g) else "train" for g in groups}
    assignments[next(g for g in groups if not confirmation(g))] = "dev"
    return {
        "scenario_id": "P100-020",
        "assets": [{"role": "coral_netcdf", "path": "raw/map.nc"}],
        "group_assignments": assignments,
        "input_units": INPUT_UNITS,
        "output_units": "degree C",
    }


@pytest.fixture
def hdf(tmp_path):
    path = tmp_path / "map.nc"
    with h5py.File(path, "w") as f:
        f.attrs.update(ROOT_IDENTITY)
        for name, dtype in [(VARIABLE, "i2"), ("mask", "u1")]:
            ds = f.create_dataset(
                name,
                shape=(1, 3600, 7200),
                dtype=dtype,
                chunks=(1, 40, 40),
                shuffle=True,
                compression="gzip",
                fillvalue=0,
            )
            ds.attrs.update({"_Netcdf4Coordinates": [0, 2, 1], "grid_mapping": "crs"})
        f[VARIABLE].attrs.update(
            {
                "units": "degree_Celsius",
                "scale_factor": [0.01],
                "_FillValue": [-32768],
                "valid_min": [-1500],
                "valid_max": [1500],
            }
        )
        f["mask"].attrs.update(
            {
                "units": "pixel_classification",
                "flag_meanings": "valid-water land missing ice",
                "coordinates": "time lat lon",
                "flag_values": [0, 1, 2, 4],
                "_FillValue": [251],
            }
        )
        for name, values, unit, axis in [
            ("lat", np.linspace(89.975, -89.975, 3600).astype("f4"), "degrees_north", "Y"),
            ("lon", np.linspace(-179.975, 179.975, 7200).astype("f4"), "degrees_east", "X"),
            ("time", np.array([1439726400], dtype="i4"), "seconds since 1981-01-01 00:00:00", "T"),
        ]:
            ds = f.create_dataset(name, data=values, shuffle=True, compression="gzip")
            ds.attrs.update(units=unit, axis=axis)
        ds = f.create_dataset("crs", data=np.int16(-32767))
        ds.attrs.update(grid_mapping_name="latitude_longitude", epsg_code="EPSG:4326")
    return path


def test_planar_stencil_has_exact_center_means_and_float32_latitude(grid):
    records, diag = sample_map(*grid)
    assert len(records) == 162 and diag["candidate_centers"] == 162
    r = records[0]
    assert r["response"] == -9.4
    assert all(
        r["values"][k] == pytest.approx(r["response"]) for k in ["hx", "hy", "ox", "oy", "dg"]
    )
    assert r["values"]["gx"] == pytest.approx(0.16) and r["values"]["gy"] == pytest.approx(0.08)
    assert r["values"]["clat"] == float(np.cos(np.deg2rad(grid[2][20])))
    assert r["neighbors"] == [(20 + dy, 20 + dx) for dy, dx in OFFSETS]
    assert diag["target_input_pixel_intersection"] == diag["reused_input_pixels"] == 0


def test_every_target_is_excluded_from_all_predictors_and_test_exports(grid):
    before, _ = sample_map(*grid)
    recipe = make_recipe(before)
    parts, lineage, check = build_rows(recipe, before)
    assert check["valid"] and all("target" not in r for r in parts["test"])
    raw, mask, lat, lon = grid
    for r in before:
        raw[r["y"], r["x"]] += 10
    after, _ = sample_map(raw, mask, lat, lon)
    new, newlineage, _ = build_rows(recipe, after)
    assert parts["test"] == new["test"] and lineage == newlineage
    for a, b in zip(before, after, strict=True):
        assert a["values"] == b["values"] and b["response"] == pytest.approx(a["response"] + 0.1)
    assert not any("response" in a for a in lineage)
    assert all(a["stencil_id"] == PARSER and "input_pixels" not in a for a in lineage)


def test_neighbor_changes_only_one_rule_input_without_affecting_targets(grid):
    before, _ = sample_map(*grid)
    grid[0][20, 16] += 10
    after, _ = sample_map(*grid)
    assert all(a["response"] == b["response"] for a, b in zip(before, after, strict=True))
    assert sum(a["values"] != b["values"] for a, b in zip(before, after, strict=True)) == 1


@pytest.mark.parametrize(
    "where,flag,value",
    [(0, 1, 0), (1, 2, 0), (2, 4, 0), (3, 251, 0), (0, 0, -32768), (1, 0, 1501), (2, 0, -1501)],
)
def test_invalid_or_missing_center_and_neighbor_not_imputed(grid, where, flag, value):
    positions = [(20, 20), *((20 + dy, 20 + dx) for dy, dx in OFFSETS)]
    y, x = positions[where]
    grid[0][y, x] = value
    grid[1][y, x] = flag
    records, diag = sample_map(*grid)
    assert len(records) == 161 and diag["excluded_centers"] == 1
    assert all((r["y"], r["x"]) != (20, 20) for r in records)
    assert (
        diag["exclusion_reason_counts"][
            ("non_water_stencil" if flag else "invalid_or_fill_stencil")
        ]
        == 1
    )


def test_sixty_degree_scope_and_inclusive_native_range(grid):
    grid[2][20] = 61
    grid[0][60, 20] = 1500
    rows, diag = sample_map(*grid)
    assert diag["candidate_centers"] == 144
    assert all(r["y"] != 20 for r in rows)
    assert next(r for r in rows if r["y"] == 60 and r["x"] == 20)["response"] == 15


def test_original_confirmation_group_and_identity_guards(grid):
    records, _ = sample_map(*grid)
    recipe = make_recipe(records)
    parts, _, _ = build_rows(recipe, records)
    r = records[0]
    p = recipe["group_assignments"][r["group"]]
    assert identity("P100-020", "sample", "pixel-20-20") in {a["sample_id"] for a in parts[p]}
    bad = deepcopy(recipe)
    bad["group_assignments"][
        next(g for g, p in bad["group_assignments"].items() if p == "test")
    ] = "train"
    with pytest.raises(ValueError, match="confirmation"):
        build_rows(bad, records)
    bad = deepcopy(recipe)
    bad["group_assignments"]["invented"] = "dev"
    with pytest.raises(ValueError, match="independent-unit assignments"):
        build_rows(bad, records)
    bad = deepcopy(recipe)
    bad["input_units"]["hx"] = "kelvin"
    with pytest.raises(ValueError, match="units"):
        reconstruct_coral(bad, None)


@pytest.mark.parametrize("kind", ["mask", "shape", "dtype", "lat", "lon"])
def test_invalid_grid_rejected_before_processing(grid, kind):
    raw, mask, lat, lon = grid
    if kind == "mask":
        mask = mask[:10]
    if kind == "shape":
        raw = raw[:10]
    if kind == "dtype":
        raw = raw.astype(float)
    if kind == "lat":
        lat[0] = np.nan
    if kind == "lon":
        lon[0] = 181
    with pytest.raises(ValueError, match="grid"):
        sample_map(raw, mask, lat, lon)


def test_full_native_grid_schema_filters_and_binding(hdf):
    arrays, inventory = native_arrays(hdf)
    assert arrays[VARIABLE].shape == (3600, 7200)
    assert inventory[0]["filters"] == [2, 1]
    assert inventory[0]["expanded_bytes"] == 51840000
    env = runtime_binding(PARSER)
    assert env["native_decoder"]["h5py"] == h5py.__version__
    assert "principia_asd.catalog.coral" in env["module_hashes"]


@pytest.mark.parametrize(
    "name,key,value",
    [
        (VARIABLE, "units", "kelvin"),
        (VARIABLE, "scale_factor", [1]),
        (VARIABLE, "add_offset", [273.15]),
        (VARIABLE, "_FillValue", [-9999]),
        ("mask", "flag_meanings", "valid-water ice missing land"),
        ("mask", "_Netcdf4Coordinates", [0, 1, 2]),
        ("time", "units", "days since 1981-01-01"),
        ("crs", "epsg_code", "EPSG:3857"),
    ],
)
def test_unit_mask_and_calibration_mutation_rejected(hdf, name, key, value):
    with h5py.File(hdf, "a") as f:
        f[name].attrs[key] = value
    with pytest.raises(ValueError, match="differs|differ"):
        native_arrays(hdf)


@pytest.mark.parametrize("name", ["lat", "lon", "time"])
def test_coordinate_or_clock_mutation_rejected(hdf, name):
    with h5py.File(hdf, "a") as f:
        f[name][0] += 1
    with pytest.raises(ValueError, match="coordinate grid or observation clock"):
        native_arrays(hdf)


def test_version_identity_and_unexpected_mask_rejected(hdf):
    with h5py.File(hdf, "a") as f:
        f.attrs["product_version"] = "3.2"
    with pytest.raises(ValueError, match="identity"):
        native_arrays(hdf)
    with h5py.File(hdf, "a") as f:
        f.attrs["product_version"] = "3.1"
        f["mask"][0, 0, 0] = 3
    with pytest.raises(ValueError, match="Undeclared"):
        native_arrays(hdf)


@pytest.mark.parametrize(
    "kind", ["soft", "external", "virtual", "storage", "lzf", "shape", "dtype"]
)
def test_indirect_unsupported_and_unbounded_storage_rejected(hdf, kind, tmp_path):
    with h5py.File(hdf, "a") as f:
        del f[VARIABLE]
        if kind == "soft":
            f[VARIABLE] = h5py.SoftLink("/mask")
        elif kind == "external":
            f[VARIABLE] = h5py.ExternalLink("forbidden.h5", "/response")
        elif kind == "virtual":
            layout = h5py.VirtualLayout(shape=(10,), dtype="i2")
            layout[:] = h5py.VirtualSource("forbidden.h5", "/response", shape=(10,))
            f.create_virtual_dataset(VARIABLE, layout)
        elif kind == "storage":
            f.create_dataset(
                VARIABLE, shape=(10,), dtype="i2", external=[(str(tmp_path / "forbidden"), 0, 20)]
            )
        elif kind == "lzf":
            f.create_dataset(VARIABLE, shape=(10,), dtype="i2", compression="lzf")
        elif kind == "shape":
            f.create_dataset(VARIABLE, shape=(1, 3600, 7201), dtype="i2")
        else:
            f.create_dataset(VARIABLE, shape=(1, 3600, 7200), dtype="f4")
    with pytest.raises(ValueError, match="indirect|virtual|External|filter|shape or dtype"):
        native_arrays(hdf)


def test_byte_bound_before_hdf_open(tmp_path):
    p = tmp_path / "large.nc"
    with p.open("wb") as f:
        f.truncate(30000001)
    with pytest.raises(ValueError, match="Oversized"):
        native_arrays(p)


def test_nested_name_denied_before_dereference(hdf):
    with h5py.File(hdf, "r") as f:
        with pytest.raises(ValueError, match="indirect"):
            local_dataset(f, "group/data")
