import json
import struct
import zipfile
import zlib
from copy import deepcopy

import numpy as np
import pytest
from scipy.io import savemat

from principia_asd.catalog.microscopy import INPUT_UNITS, MAX_ELEMENT, sampling_grid, stored_map
from principia_asd.catalog.native import identity, reconstruct
from principia_asd.io import file_sha


@pytest.fixture
def maps():
    y, x = np.indices((240, 360))
    a = 0.25 + y / 900 - x / 1000 + np.sin(x / 7) * 0.01
    return {
        sp: {
            "Bt": np.ones_like(a),
            "Bz": a.copy(),
            "corners": np.array([[1, 1], list(a.shape)], dtype=float),
            "h": np.array([[5e-6]]),
            "newLED": np.zeros_like(a),
            "step": np.array([[1.17e-6]]),
        }
        for sp in ["CSH", "CSL"]
    }


def save(tmp_path, maps, compressed=True):
    for sp, data in maps.items():
        savemat(tmp_path / f"{sp}.mat", data, do_compression=compressed)
    (tmp_path / "source.json").write_text(
        json.dumps(
            {
                "id": 14776881,
                "doi": "10.5281/zenodo.14776881",
                "metadata": {"license": {"id": "cc-by-4.0"}},
            }
        )
    )
    with zipfile.ZipFile(tmp_path / "source.docx", "w") as z:
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>CSH_FOV5_Bz_uz0.mat CSL_FOV4_Bz_uz0.mat 119DOA 129DOA MCMC parameter estimation</w:t></w:r></w:p></w:document>',
        )
    groups = {
        f"{sp}-r{y // 200:02d}-c{x // 320:02d}"
        for sp in maps
        for y, x in sampling_grid(maps[sp]["Bz"].shape)[0]
    }
    return {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-070",
        "parser": "microscopy-native-bz-stencil-v1",
        "input_units": INPUT_UNITS.copy(),
        "output_units": "source-native Bz unit (SI conversion unresolved)",
        "group_assignments": {
            g: "test" if g.startswith("CSL") else "dev" if g == "CSH-r00-c01" else "train"
            for g in groups
        },
        "assets": [
            {
                "path": name,
                "bytes": (tmp_path / name).stat().st_size,
                "sha256": file_sha(tmp_path / name),
                "role": role,
            }
            for name, role in [
                ("CSH.mat", "CSH_map"),
                ("CSL.mat", "CSL_map"),
                ("source.json", "source_metadata"),
                ("source.docx", "source_readme"),
            ]
        ],
    }


@pytest.mark.parametrize("compressed", [False, True])
def test_numeric_mat_custody_and_exact_pixel_operations(tmp_path, maps, compressed):
    recipe = save(tmp_path, maps, compressed)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert {s: len(v) for s, v in parts.items()} == {"train": 169, "dev": 18, "test": 187}
    assert checks["split_check"]["valid"]
    audit = checks["microscopy_validation"]
    assert audit["declared_whole_strip_check"]["shared_split_units"] == {
        "CSH-r00": ["dev", "train"]
    }
    assert not audit["declared_whole_strip_check"]["valid"]
    assert audit["maps"]["CSL"]["target_centers"] == 187
    assert audit["maps"]["CSL"]["unique_predictor_pixels"] == 187 * 12
    assert audit["maps"]["CSL"]["target_predictor_overlap"] == 0
    assert audit["readme"]["map_suffix_in_readme"] == "uz0"
    assert parts["train"][0]["sample_id"] == identity("P100-070", "sample", "CSH-20-20")
    assert parts["train"][0]["target"] == maps["CSH"]["Bz"][20, 20]
    assert parts["train"][0]["hx"] == (maps["CSH"]["Bz"][20, 16] + maps["CSH"]["Bz"][20, 24]) / 2
    assert lineage[0]["center_zero_based_yx"] == [20, 20]
    assert audit["fit_count"] == 0 and audit["learned_transformations"] == []
    assert not any("target" in r for r in parts["test"])


def test_finite_test_centers_and_other_response_channels_cannot_affect_inputs(tmp_path, maps):
    before = reconstruct(save(tmp_path, maps), tmp_path)
    changed = deepcopy(maps)
    for y, x in sampling_grid(changed["CSL"]["Bz"].shape)[0]:
        changed["CSL"]["Bz"][y, x] = 123456.789
    for fields in changed.values():
        fields["Bt"][:] = np.nan
        fields["newLED"][:] = 123456.789
    after = reconstruct(save(tmp_path, changed), tmp_path)
    assert before == after
    assert "123456.789" not in json.dumps(after)


def test_nonfinite_source_exclusions_are_preserved(tmp_path, maps):
    maps["CSH"]["Bz"][20, 20] = np.nan
    maps["CSL"]["Bz"][20, 16] = np.nan
    parts, _, checks = reconstruct(save(tmp_path, maps), tmp_path)
    assert len(parts["train"]) == 168 and len(parts["test"]) == 186
    assert checks["microscopy_validation"]["maps"]["CSH"]["excluded_nonfinite_stencils"] == [
        {"center": [20, 20], "nonfinite_offsets": [0]}
    ]
    assert checks["microscopy_validation"]["maps"]["CSL"]["excluded_nonfinite_stencils"] == [
        {"center": [20, 20], "nonfinite_offsets": [1]}
    ]


@pytest.mark.parametrize(
    "change,match",
    [
        ("complex", "real dense"),
        ("single", "real dense"),
        ("object", "real dense"),
        ("wrong_shape", "shapes"),
        ("transpose", "shapes"),
        ("corners", "geometry"),
        ("step", "geometry"),
        ("h", "geometry"),
        ("extra_variable", "Unexpected"),
        ("missing", "Missing"),
        ("unknown_name", "Unexpected"),
    ],
)
def test_reject_untrusted_map_layouts(tmp_path, maps, change, match):
    d = maps["CSH"]
    if change == "complex":
        d["Bz"] = d["Bz"].astype(complex) + 1j
    elif change == "single":
        d["Bz"] = d["Bz"].astype(np.float32)
    elif change == "object":
        d["Bz"] = np.array([["malicious"]], dtype=object)
    elif change == "wrong_shape":
        d["Bt"] = d["Bt"][:-1]
    elif change == "transpose":
        d["Bz"] = d["Bz"].T
    elif change == "corners":
        d["corners"][0, 0] = 0
    elif change == "step":
        d["step"][0, 0] = 0
    elif change == "h":
        d["h"][0, 0] = np.nan
    elif change == "extra_variable":
        d["hidden"] = np.array([[1.0]])
    elif change == "missing":
        del d["step"]
    elif change == "unknown_name":
        d["temperature"] = d.pop("Bz")
    savemat(tmp_path / "bad.mat", d, do_compression=True)
    with pytest.raises(ValueError, match=match):
        stored_map(tmp_path / "bad.mat")


@pytest.mark.parametrize(
    "change,match",
    [
        ("version", "Unsupported"),
        ("subsystem", "Unsupported"),
        ("truncated", "Missing"),
        ("duplicate", "Duplicate"),
        ("corrupt", "Corrupt"),
        ("expanded", "Oversized"),
        ("trailing", "trailing"),
    ],
)
def test_bounded_mat_bytes_and_expansion(tmp_path, maps, change, match):
    save(tmp_path, maps)
    path = tmp_path / "CSH.mat"
    raw = path.read_bytes()
    size = struct.unpack_from("<I", raw, 132)[0]
    first = raw[128 : 136 + size]
    if change == "version":
        raw = raw[:124] + b"\x00\x02IM" + raw[128:]
    elif change == "subsystem":
        raw = raw[:116] + b"\x01" * 8 + raw[124:]
    elif change == "truncated":
        raw = raw[:135]
    elif change == "duplicate":
        raw = raw[:128] + first + first + raw[136 + size :]
    elif change == "corrupt":
        raw = raw[:136] + b"xxxx" + raw[140:]
    elif change == "expanded":
        bomb = zlib.compress(b"x" * (MAX_ELEMENT + 1))
        raw = raw[:128] + struct.pack("<II", 15, len(bomb)) + bomb
    elif change == "trailing":
        raw += b"not-a-map"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match=match):
        stored_map(path)


def test_units_specimen_split_and_source_binding(tmp_path, maps):
    r = save(tmp_path, maps)
    r["input_units"]["hx"] = "Tesla"
    with pytest.raises(ValueError, match="unit"):
        reconstruct(r, tmp_path)
    r = save(tmp_path, maps)
    r["group_assignments"]["CSL-r00-c00"] = "train"
    with pytest.raises(ValueError, match="specimen/partition"):
        reconstruct(r, tmp_path)
    r = save(tmp_path, maps)
    r["group_assignments"]["CSH-r99-c99"] = "dev"
    with pytest.raises(ValueError, match="independent-unit"):
        reconstruct(r, tmp_path)
    r = save(tmp_path, maps)
    (tmp_path / "CSL.mat").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(r, tmp_path)


def test_all_zero_stencil_has_finite_zero_contrast(tmp_path, maps):
    for fields in maps.values():
        fields["Bz"][:] = 0
    parts, _, _ = reconstruct(save(tmp_path, maps), tmp_path)
    for rows in parts.values():
        for r in rows:
            assert r["gx"] == r["gy"] == 0


def test_matlab_compact_integer_storage_preserves_double_class(tmp_path, maps):
    from principia_asd.catalog.microscopy import _element

    save(tmp_path, maps)
    path = tmp_path / "CSH.mat"
    raw = path.read_bytes()
    output, position = raw[:128], 128

    def encode(kind, payload):
        return struct.pack("<II", kind, len(payload)) + payload + b"\x00" * (-len(payload) % 8)

    while position < len(raw):
        kind, size = struct.unpack_from("<II", raw, position)
        decoded = zlib.decompress(raw[position + 8 : position + 8 + size])
        _, matrix, _ = _element(decoded, 0)
        fields, cursor = [], 0
        for _ in range(4):
            kind, payload, cursor = _element(matrix, cursor)
            fields.append((kind, bytes(payload)))
        name = fields[2][1].decode()
        if name == "corners":
            fields[3] = (4, np.array(maps["CSH"]["corners"], dtype="<u2").tobytes(order="F"))
        elif name == "newLED":
            fields[3] = (2, np.array(maps["CSH"]["newLED"], dtype="u1").tobytes(order="F"))
        payload = zlib.compress(encode(14, b"".join(encode(k, v) for k, v in fields)))
        output += struct.pack("<II", 15, len(payload)) + payload
        position += size + 8
    path.write_bytes(output)
    values, metadata = stored_map(path)
    np.testing.assert_array_equal(values, maps["CSH"]["Bz"])
    assert metadata["corners"] == [[1, 1], [240, 360]]
