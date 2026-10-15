import copy
import csv
import io
import json

import numpy as np
import pytest

from principia_asd.catalog.native import identity, reconstruct
from principia_asd.catalog.rydberg import (
    FILENAME,
    HEADER,
    decode_grid,
    original_assignments,
    reconstruct_rydberg,
)
from principia_asd.io import file_sha


def grid_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(HEADER)
    writer.writerows(rows)
    return stream.getvalue().encode()


def fixture(tmp_path):
    # Full 300-coordinate block policy with a smaller detuning inventory.
    rows = [
        [x, 0.5 + j * 0.02, (x + j - 100) / 100] for x in [-61, -60, 0, 60, 61] for j in range(300)
    ]
    path = tmp_path / FILENAME
    path.write_bytes(grid_bytes(rows))
    asset = {
        "role": "ion_spectral_grid",
        "path": FILENAME,
        "sha256": file_sha(path),
        "bytes": path.stat().st_size,
    }
    meta = {
        "doi": "doi:10.18434/mds2-3951",
        "version": "1.0.3",
        "components": [
            {
                "filepath": FILENAME,
                "size": asset["bytes"],
                "checksum": {"algorithm": {"tag": "sha256"}, "hash": asset["sha256"]},
            }
        ],
    }
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(meta))
    documentation = tmp_path / "excluded-fits.txt"
    documentation.write_text("Author-fitted summaries are not predictors")
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-006",
        "parser": "rydberg-ion-source-grid-v1",
        "source_version": "1.0.3",
        "source_grid_shape": [5, 300],
        "assets": [
            asset,
            {
                "role": "nist_source_record",
                "path": metadata.name,
                "bytes": metadata.stat().st_size,
                "sha256": file_sha(metadata),
            },
            {
                "role": "excluded_fitted_summary_documentation",
                "path": documentation.name,
                "bytes": documentation.stat().st_size,
                "sha256": file_sha(documentation),
            },
        ],
        "group_assignments": original_assignments(
            "P100-006", {f"rabi-block-{i:02d}" for i in range(10)}
        ),
    }
    return recipe, rows, meta


def test_exact_spectral_domain_source_rows_units_and_nonpositive_signals(tmp_path):
    recipe, _, _ = fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert {s: len(v) for s, v in parts.items()} == {"train": 540, "dev": 180, "test": 180}
    assert checks["split_check"]["valid"]
    inventory = checks["spectral_validation"]
    assert inventory["source_grid_rows"] == 1500
    assert inventory["outside_domain_rows"] == 600
    assert inventory["selected_detuning_coordinates"] == 3
    assert inventory["instrument_sampling_or_grid_interpolation"] == "not_resolved"
    assert len(lineage) == 900
    assert min(r["source_row"] for r in lineage) == 302
    assert max(r["source_row"] for r in lineage) == 1201
    assert all("target" not in r for r in parts["test"])
    assert {r["detuning_MHz"] for rs in parts.values() for r in rs} == {-60.0, 0.0, 60.0}
    assert any(r["target"] <= 0 for r in parts["train"])
    expected = identity("P100-006", "sample", f"P100-006:{FILENAME}:row302")
    assert expected in {r["sample_id"] for rs in parts.values() for r in rs}
    assert checks["frequency_convention"].startswith("Stored delta_c/(2*pi)")


def test_heldout_responses_and_author_fits_do_not_change_inputs(tmp_path):
    recipe, rows, _ = fixture(tmp_path)
    before = reconstruct_rydberg(recipe, tmp_path)[0]
    for i, r in enumerate(rows):
        if recipe["group_assignments"][f"rabi-block-{(i % 300) // 30:02d}"] == "test":
            r[2] = -98765
    (tmp_path / FILENAME).write_bytes(grid_bytes(rows))
    (tmp_path / "excluded-fits.txt").write_text("Entire fitted summary changed")
    assert reconstruct_rydberg(recipe, tmp_path)[0] == before
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, tmp_path)


def test_nonfinite_source_response_is_preserved_as_an_exclusion(tmp_path):
    recipe, rows, _ = fixture(tmp_path)
    rows[300][2] = float("nan")
    rows[1000][2] = ""
    rows[0][2] = float("inf")
    (tmp_path / FILENAME).write_bytes(grid_bytes(rows))
    parts, _, checks = reconstruct_rydberg(recipe, tmp_path)
    assert sum(len(r) for r in parts.values()) == 898
    assert checks["spectral_validation"]["nonfinite_response_rows_total"] == 3
    assert checks["spectral_validation"]["nonfinite_response_rows_in_domain"] == 2
    assert checks["excluded_rows"] == [
        {"source_row": 302, "reason": "nonfinite_source_response"},
        {"source_row": 1002, "reason": "nonfinite_source_response"},
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_coordinate",
        "reordered_rows",
        "missing_point",
        "nonrectangular",
        "nan_coordinate",
        "negative_rabi",
        "zero_rabi",
        "formula_coordinate",
        "extra_column",
        "malformed_response",
    ],
)
def test_invalid_source_grid_is_rejected(tmp_path, mutation):
    _, rows, _ = fixture(tmp_path)
    if mutation == "duplicate_coordinate":
        rows[301][:2] = rows[300][:2]
    elif mutation == "reordered_rows":
        rows[0], rows[1] = rows[1], rows[0]
    elif mutation == "missing_point":
        rows.pop()
    elif mutation == "nonrectangular":
        rows[0][0] = -62
    elif mutation == "nan_coordinate":
        rows[0][0] = float("nan")
    elif mutation == "negative_rabi":
        rows[0][1] = -1
    elif mutation == "zero_rabi":
        rows[0][1] = 0
    elif mutation == "formula_coordinate":
        rows[0][0] = "=1+2"
    elif mutation == "extra_column":
        rows[0].append(999)
    elif mutation == "malformed_response":
        rows[0][2] = "=reference!A1"
    with pytest.raises(ValueError):
        decode_grid(grid_bytes(rows))


def test_units_header_multiline_rows_and_allocation_bounds_fail(tmp_path):
    _, rows, _ = fixture(tmp_path)
    raw = grid_bytes(rows)
    with pytest.raises(ValueError, match="units"):
        decode_grid(raw.replace(b"Ion Amplitude", b"EIT Amplitude"))
    with pytest.raises(ValueError, match="units"):
        decode_grid(raw.replace(b"MHz", b"Hz"))
    with pytest.raises(ValueError, match="multiline"):
        decode_grid(raw.replace(b"-61,0.5,", b'"-61\n",0.5,', 1))
    with pytest.raises(ValueError, match="Excessive"):
        decode_grid(raw, max_rows=10)
    with pytest.raises(ValueError, match="bounded"):
        decode_grid(b" " * 16_000_001)


@pytest.mark.parametrize(
    "mutation",
    [
        "doi",
        "version",
        "component_hash",
        "component_size",
        "component_algorithm",
        "duplicate_component",
        "inventory",
        "test_allocation",
        "dev_allocation",
        "missing_group",
        "unknown_group",
        "source_name",
    ],
)
def test_wrong_source_bindings_and_split_policies_fail(tmp_path, mutation):
    recipe, _, meta = fixture(tmp_path)
    if mutation == "doi":
        meta["doi"] = "doi:other"
    elif mutation == "version":
        meta["version"] = "later"
    elif mutation == "component_hash":
        meta["components"][0]["checksum"]["hash"] = "0" * 64
    elif mutation == "component_size":
        meta["components"][0]["size"] += 1
    elif mutation == "component_algorithm":
        meta["components"][0]["checksum"]["algorithm"]["tag"] = "md5"
    elif mutation == "duplicate_component":
        meta["components"].append(copy.deepcopy(meta["components"][0]))
    elif mutation == "inventory":
        recipe["source_grid_shape"] = [6, 300]
    elif mutation == "test_allocation":
        recipe["group_assignments"]["rabi-block-06"] = "train"
    elif mutation == "dev_allocation":
        train = next(g for g, s in recipe["group_assignments"].items() if s == "train")
        dev = next(g for g, s in recipe["group_assignments"].items() if s == "dev")
        recipe["group_assignments"][train] = "dev"
        recipe["group_assignments"][dev] = "train"
    elif mutation == "missing_group":
        recipe["group_assignments"].pop("rabi-block-00")
    elif mutation == "unknown_group":
        recipe["group_assignments"]["rabi-block-10"] = "train"
    elif mutation == "source_name":
        recipe["assets"][0]["path"] = "other-spectrum.csv"
    (tmp_path / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError):
        reconstruct_rydberg(recipe, tmp_path)


def test_source_coordinate_block_cannot_disappear_through_missingness(tmp_path):
    recipe, rows, _ = fixture(tmp_path)
    for i, row in enumerate(rows):
        if i % 300 < 30:
            row[2] = np.nan
    (tmp_path / FILENAME).write_bytes(grid_bytes(rows))
    with pytest.raises(ValueError, match="no eligible"):
        reconstruct_rydberg(recipe, tmp_path)


def test_target_change_does_not_change_block_membership(tmp_path):
    recipe, rows, _ = fixture(tmp_path)
    parts, _, checks = reconstruct_rydberg(recipe, tmp_path)
    for row in rows:
        row[2] = -row[2]
    (tmp_path / FILENAME).write_bytes(grid_bytes(rows))
    changed, _, newchecks = reconstruct_rydberg(recipe, tmp_path)
    for split in parts:
        assert [(r["sample_id"], r["group"]) for r in parts[split]] == [
            (r["sample_id"], r["group"]) for r in changed[split]
        ]
    assert checks["block_inventory"] == newchecks["block_inventory"]


def test_original_confirmation_requires_whole_registered_blocks():
    with pytest.raises(ValueError, match="confirmation"):
        original_assignments("P100-006", {"rabi-block-00"})
