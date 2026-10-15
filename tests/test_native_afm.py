import io
import json
import stat
import zipfile

import numpy as np
import pytest

from principia_asd.catalog.afm import (
    HEADER,
    INPUT_UNITS,
    SURFACES,
    archive_members,
    calibrated_features,
    instrument_header,
    member_identity,
    original_assignments,
    reconstruct_afm,
    stored_curve,
)
from principia_asd.catalog.native import reconstruct
from principia_asd.io import file_sha


def header():
    return (
        b"\\*Force file list\r\n\\Spring Constant: 20\r\n"
        b"\\@Sens. DeflSens: V 60 nm/V\r\n"
        b"\\@Sens. ForceDeflSens: V 1200 nN/V\r\n"
        b"\\Date: 12:00:00 Mon Aug 07 2023\r\n\\*File list end\r\n"
    )


def values():
    ramp = np.arange(128, dtype=float)
    approach = np.maximum(0, ramp - 70) * 1000  # pN; first +5nN crossing at index75.
    retract = np.linspace(40_000, -2000, 128)
    return np.column_stack(
        [ramp, ramp[::-1], approach / 20_000, retract / 20_000, approach, retract]
    )


def encode(a):
    out = io.StringIO()
    out.write("\t".join(HEADER) + "\t\r\n")
    np.savetxt(out, a, fmt="%.12e", delimiter="\t")
    return out.getvalue().encode()


def panel():
    result = {}
    for surface, count in SURFACES.items():
        prefix = {
            "CA Flat": "230804_CA_Flat",
            "CA Low Roughness": "230804_CA_Low",
            "CA High Roughness": "230807_CA_high",
        }[surface]
        for j in range(count):
            name = (
                f"NFFA DESY Raw data/{surface}/{prefix}.0_00002.pfc-A0_ForceCurveIndex_{j}.spm.txt"
            )
            result[name] = encode(values())
            result[name[:-4]] = header()
    return result


def write_zip(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, raw in entries.items():
            z.writestr(name, raw)


def fixture(tmp_path):
    entries = panel()
    archive = tmp_path / "afm.zip"
    write_zip(archive, entries)
    meta = tmp_path / "metadata.json"
    meta.write_text(
        json.dumps(
            {
                "id": 20281797,
                "doi": "10.5281/zenodo.20281797",
                "metadata": {"license": {"id": "cc-by-4.0"}},
            }
        )
    )
    members = sorted(n for n in entries if n.endswith(".txt"))
    return {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-084",
        "parser": "cellulose-afm-calibrated-retraction-v1",
        "input_units": INPUT_UNITS.copy(),
        "output_units": "nN",
        "curve_members": members,
        "group_assignments": original_assignments("P100-084", members),
        "assets": [
            {"path": p.name, "role": role, "bytes": p.stat().st_size, "sha256": file_sha(p)}
            for p, role in [(archive, "afm_archive"), (meta, "source_metadata")]
        ],
    }


def test_exact_calibration_units_and_permitted_prefix():
    a = stored_curve(encode(values()), instrument_header(header()))
    rows, cross = calibrated_features(a)
    assert cross == 75 and len(rows) == 112
    assert rows[0]["x"] == pytest.approx((111 - 75) / (127 - 75))
    assert rows[0]["base"] == 0
    assert rows[0]["amp"] == pytest.approx(values()[:5, 5].mean() / 1000)
    assert rows[0]["progress"] == pytest.approx(16 / 127)
    assert rows[-1]["x"] == pytest.approx(-75 / 52)  # Negative coordinates retained, no clipping.


def test_complete_curve_custody_and_target_free_test_inputs(tmp_path):
    recipe = fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert {s: len(r) for s, r in parts.items()} == {"train": 896, "dev": 224, "test": 336}
    assert not any("target" in row for row in parts["test"])
    assert checks["split_check"]["valid"]
    assert checks["afm_validation"]["source_rows"] == 1664
    assert len(lineage) == 1456 and lineage[0]["source_row"] == 18
    assert lineage[-1]["source_row"] == 129
    assert checks["afm_validation"]["readme_sensitivity_matches_headers"] is False
    assert set(parts["train"][0]) == {
        "sample_id",
        "group",
        "target",
        "x",
        "base",
        "amp",
        "progress",
    }


@pytest.mark.parametrize("split", ["train", "test"])
def test_late_force_and_its_alias_never_change_predictors(tmp_path, split):
    recipe = fixture(tmp_path)
    before, _, _ = reconstruct_afm(recipe, tmp_path)
    selected = next(
        n
        for n in recipe["curve_members"]
        if recipe["group_assignments"][member_identity(n)[0]] == split
    )
    entries = panel()
    a = values()
    a[16:, 5] += 1234
    a[16:, 3] = a[16:, 5] / 20_000
    entries[selected] = encode(a)
    write_zip(tmp_path / "afm.zip", entries)
    after, _, _ = reconstruct_afm(recipe, tmp_path)
    def strip(rows):
        return [{k: v for k, v in r.items() if k != "target"} for r in rows]
    assert {s: strip(v) for s, v in before.items()} == {s: strip(v) for s, v in after.items()}
    assert (before != after) == (split == "train")


def test_unused_middle_retraction_cannot_change_inputs_or_denominator():
    a = values()
    rows, _ = calibrated_features(a)
    a[5:16, 3:6:2] += 900000
    assert calibrated_features(a)[0] == rows
    a[:, 3] = -999999  # Direct feature compiler does not use the response alias.
    assert calibrated_features(a)[0] == rows


def test_missing_crossing_and_degenerate_coordinate_fail_whole_task():
    a = values()
    a[:, 4] = 0
    with pytest.raises(ValueError, match="crossing"):
        calibrated_features(a)
    a = values()
    a[:, 4] = 0
    a[-1, 4] = 6000
    with pytest.raises(ValueError, match="Degenerate"):
        calibrated_features(a)


@pytest.mark.parametrize("change", ["units", "nonfinite", "columns", "rows", "ramp", "force_alias"])
def test_measurement_unit_shape_clock_and_calibration_guards(change):
    a = values()
    raw = encode(a)
    if change == "units":
        raw = raw.replace(b"Defl_pN_Rt", b"Defl_nN_Rt")
    if change == "nonfinite":
        a[50, 5] = np.nan
        raw = encode(a)
    if change == "columns":
        raw = encode(np.column_stack([a, np.zeros(128)]))
    if change == "rows":
        raw = encode(a[:-1])
    if change == "ramp":
        a[30, 1] = a[29, 1] + 1
        raw = encode(a)
    if change == "force_alias":
        a[20, 5] *= 2
        raw = encode(a)
    with pytest.raises(ValueError):
        stored_curve(raw, instrument_header(header()))


@pytest.mark.parametrize("change", ["duplicate", "unit", "inconsistent", "missing", "oversized"])
def test_instrument_metadata_guards(change):
    raw = header()
    if change == "duplicate":
        raw = raw.replace(b"\\Spring Constant:", b"\\Spring Constant: 20\r\n\\Spring Constant:")
    if change == "unit":
        raw = raw.replace(b"nm/V", b"um/V")
    if change == "inconsistent":
        raw = raw.replace(b"1200", b"1300")
    if change == "missing":
        raw = raw.replace(b"\\*File list end", b"none")
    if change == "oversized":
        raw += b"0" * 100_001
    with pytest.raises(ValueError):
        instrument_header(raw)


@pytest.mark.parametrize(
    "change", ["missing", "pair", "unsafe", "symlink", "oversized", "duplicate"]
)
def test_archive_integrity_and_resource_bounds(tmp_path, change):
    entries = panel()
    p = tmp_path / "bad.zip"
    if change == "missing":
        entries.pop(next(n for n in entries if n.endswith(".txt")))
    if change == "pair":
        entries.pop(next(n for n in entries if n.endswith(".spm")))
    if change == "unsafe":
        entries["../escape"] = b"no"
    if change == "oversized":
        entries["large"] = b"0" * 3_000_001
    write_zip(p, entries)
    if change == "symlink":
        with zipfile.ZipFile(p, "a") as z:
            i = zipfile.ZipInfo("link")
            i.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(i, "outside")
    if change == "duplicate":
        with pytest.warns(UserWarning), zipfile.ZipFile(p, "a") as z:
            z.writestr(next(iter(entries)), b"bad")
    with zipfile.ZipFile(p) as z, pytest.raises(ValueError):
        archive_members(z)


@pytest.mark.parametrize("change", ["hash", "split", "member", "units", "metadata"])
def test_source_identity_frozen_allocation_and_hashes(tmp_path, change):
    recipe = fixture(tmp_path)
    if change == "hash":
        (tmp_path / "afm.zip").write_bytes(b"changed")
    if change == "split":
        group = next(g for g, s in recipe["group_assignments"].items() if s == "train")
        recipe["group_assignments"][group] = "test"
    if change == "member":
        recipe["curve_members"].pop()
    if change == "units":
        recipe["input_units"]["base"] = "Pa"
    if change == "metadata":
        (tmp_path / "metadata.json").write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        reconstruct(recipe, tmp_path)


def test_curve_surface_identity_is_checked():
    n = next(iter(panel()))
    with pytest.raises(ValueError):
        member_identity(n.replace("CA Flat/", "CA Low Roughness/"))


def test_tiny_export_rounding_residual_is_retained():
    a = values()
    a[-1, 1] = 3.755093e-6
    result = stored_curve(encode(a), instrument_header(header()))
    assert result[-1, 1] == a[-1, 1]
