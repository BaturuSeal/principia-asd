import copy
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from principia_asd.catalog.native import (
    VERSION,
    compare_public,
    numeric_sheet,
    prepare,
    reconstruct,
)
from principia_asd.io import file_sha, read_csv, read_json, sha, write_csv, write_json


def workbook(path, *, future_shift=0.0, formula=False, bad_units=False, reverse_time=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    sheets = ["0.5 to 1 mA_cm2", "5 to 10 mA_cm2"]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(f'<sheet name="{name}" r:id="rId{j}"/>' for j, name in enumerate(sheets, 1))
            + "</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            "<Relationships>"
            + "".join(
                f'<Relationship Id="rId{j}" Target="worksheets/sheet{j}.xml"/>' for j in [1, 2]
            )
            + "</Relationships>",
        )
        for j in [1, 2]:
            header = (
                '<row r="1"><c r="A1" t="inlineStr"><is><t>'
                + ("Time, min" if bad_units else "Time, s")
                + '</t></is></c><c r="B1" t="inlineStr"><is><t>Current, μA</t></is></c></row>'
            )
            rows = []
            for k in range(33):
                row = k + 2
                # The last six observations are test; only the first three calibrate.
                y = j + k / 10 + (future_shift if k >= 27 else 0)
                t = 0 if reverse_time and k == 4 else k * 12
                f = "<f>2*A2</f>" if formula and k == 0 else ""
                rows.append(
                    f'<row r="{row}"><c r="A{row}"><v>{t}</v></c><c r="B{row}">{f}<v>{y}</v></c></row>'
                )
            z.writestr(
                f"xl/worksheets/sheet{j}.xml",
                f"<worksheet {ns}><sheetData>"
                + header
                + "".join(rows)
                + "</sheetData></worksheet>",
            )


def permeation_recipe(tmp_path, **kwargs):
    root = tmp_path / "raw-root"
    path = root / "data/traces.xlsx"
    workbook(path, **kwargs)
    recipe = {
        "schema_version": VERSION,
        "scenario_id": "P100-062",
        "parser": "hydrogen-permeation-v1",
        "historical_contract_sha256": "fixture",
        "assets": [
            {
                "role": "permeation_workbook",
                "path": "data/traces.xlsx",
                "sha256": file_sha(path),
                "bytes": path.stat().st_size,
            }
        ],
    }
    return root, path, recipe


def test_raw_reconstruction_preserves_forward_streams_lineage_and_target_custody(tmp_path):
    root, _, recipe = permeation_recipe(tmp_path)
    parts, lineage, checks = reconstruct(recipe, root)
    assert {k: len(v) for k, v in parts.items()} == {"train": 36, "dev": 12, "test": 12}
    assert checks["split_check"]["valid"]
    assert all("target" not in r for r in parts["test"])
    assert all(r["calibration_rows"] == [2, 3, 4] and r["row"] >= 5 for r in lineage)
    assert all(r["time_origin_row"] < r["row"] for r in lineage)
    assert {r["temporal_block"] for r in lineage if r["split"] == "train"} == {0, 1, 2}


def test_future_response_values_cannot_change_any_exported_measurement(tmp_path):
    root, path, recipe = permeation_recipe(tmp_path)
    before = reconstruct(recipe, root)
    workbook(path, future_shift=100000)
    with pytest.raises(ValueError, match="source hash or size"):
        reconstruct(recipe, root)
    # A new synthetic acquisition revision changes held-out values only.
    altered = copy.deepcopy(recipe)
    altered["assets"][0].update(sha256=file_sha(path), bytes=path.stat().st_size)
    assert reconstruct(altered, root) == before


@pytest.mark.parametrize("fault", ["formula", "bad_units", "reverse_time"])
def test_native_reader_rejects_unsupported_measurements(tmp_path, fault):
    _, path, _ = permeation_recipe(tmp_path, **{fault: True})
    with pytest.raises(ValueError):
        numeric_sheet(path, "0.5 to 1 mA_cm2")


def test_registered_sources_are_contained_and_identity_bound(tmp_path):
    root, path, recipe = permeation_recipe(tmp_path)
    wrong = copy.deepcopy(recipe)
    wrong["scenario_id"] = "P100-012"
    with pytest.raises(ValueError, match="identity"):
        reconstruct(wrong, root)
    wrong = copy.deepcopy(recipe)
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(path.read_bytes())
    wrong["assets"][0]["path"] = "../outside.xlsx"
    with pytest.raises(ValueError, match="leaves"):
        reconstruct(wrong, root)
    link = root / "linked.xlsx"
    link.symlink_to(outside)
    wrong["assets"][0]["path"] = "linked.xlsx"
    with pytest.raises(ValueError, match="leaves"):
        reconstruct(wrong, root)


def test_xrr_units_calibration_and_batch_split(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    recipe = {
        "schema_version": VERSION,
        "scenario_id": "P100-012",
        "parser": "hafnia-xrr-v1",
        "assets": [],
    }
    headers = [
        '*MEAS_SCAN_AXIS_X "TwoThetaOmega"',
        '*MEAS_SCAN_UNIT_X "deg"',
        '*MEAS_SCAN_UNIT_Y "counts"',
        '*HW_XG_WAVE_LENGTH_ALPHA1 "1.540593"',
        "*RAS_INT_START",
    ]
    for wafer in [1, 7, 10]:
        path = root / f"6-02-25-{wafer:02}-105-fixture.ras"
        path.write_text(
            "\n".join(
                headers
                + [f"{0.8 + k * 0.004:.6f} {1000 - k} 1" for k in range(301)]
                + ["*RAS_INT_END"]
            )
        )
        recipe["assets"].append(
            {
                "role": "xrr_ras",
                "path": path.name,
                "wafer": wafer,
                "position": "105",
                "bytes": path.stat().st_size,
                "sha256": file_sha(path),
            }
        )
    parts, lineage, checks = reconstruct(recipe, root)
    assert checks["split_check"]["units_by_partition"] == {
        "train": ["deposition-1"],
        "dev": ["deposition-3"],
        "test": ["deposition-4"],
    }
    assert len(lineage) == sum(map(len, parts.values()))
    assert all(max(a["calibration_lines"]) < a["line"] for a in lineage)
    assert all(r["outer"] == 0 for rows in parts.values() for r in rows)
    assert all("target" not in r for r in parts["test"])
    wrong = copy.deepcopy(recipe)
    wrong["assets"][0]["wafer"] = 2
    with pytest.raises(ValueError, match="wafer identity"):
        reconstruct(wrong, root)


def test_portable_draft_is_immutable_deterministic_and_replayable_without_vault(tmp_path):
    root, _, recipe = permeation_recipe(tmp_path)
    recipe_path = tmp_path / "recipe.json"
    write_json(recipe_path, recipe)
    out = tmp_path / "draft"
    result = prepare(recipe_path, root, out)
    assert result["api_calls"] == result["fitting_attempts"] == 0
    assert not result["test_targets_exported"]
    assert not result["evaluator_vault_accessed"]
    with pytest.raises(FileExistsError):
        prepare(recipe_path, root, out)
    with pytest.raises(ValueError, match="outside"):
        prepare(recipe_path, root, root / "draft")
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    write_json(frozen / "EDITION.json", {})
    with pytest.raises(ValueError, match="outside"):
        prepare(recipe_path, root, frozen / "new")
    replay = tmp_path / "replay"
    subprocess.run(
        [
            sys.executable,
            str(out / "preprocessing/prepare.py"),
            "--source-root",
            str(root),
            "--output-root",
            str(replay),
        ],
        check=True,
    )
    for path in out.rglob("*.csv.gz"):
        assert path.read_bytes() == (replay / path.relative_to(out)).read_bytes()
    assert not any("target" in row for row in read_csv(out / "public/test_inputs.csv.gz"))
    assert read_json(replay / "reconstruction.json")["status"] == "draft_not_admitted"


def test_public_parity_retains_exact_cohort_and_rejects_changed_values(tmp_path):
    root, _, recipe = permeation_recipe(tmp_path)
    parts, _, _ = reconstruct(recipe, root)
    scenario = tmp_path / "original"
    task = {"scenario_id": "P100-062", "split": {p: f"public/{p}.csv.gz" for p in parts}}
    write_json(scenario / "task-contracts/task-001.json", task)
    for p, rows in parts.items():
        write_csv(scenario / task["split"][p], rows, list(rows[0]))
    assert compare_public(parts, scenario)["status"] == "passed"
    changed = copy.deepcopy(parts)
    changed["train"][0]["target"] += 1
    with pytest.raises(ValueError, match="measurement differs"):
        compare_public(changed, scenario)
    changed["test"].pop()
    with pytest.raises(ValueError):
        compare_public(changed, scenario)
    recipe["historical_contract_sha256"] = sha(task)
    path = tmp_path / "recipe.json"
    write_json(path, recipe)
    result = prepare(path, root, tmp_path / "candidate", compare_scenario=scenario)
    assert result["historical_public_parity"]["evaluator_targets_accessed"] is False


def test_native_cli_and_existing_import_mode_validate_options(tmp_path):
    root, _, recipe = permeation_recipe(tmp_path)
    path = tmp_path / "recipe.json"
    write_json(path, recipe)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "principia_asd.cli",
            "prepare",
            "--native-recipe",
            str(path),
            "--source-root",
            str(root),
            "--output-root",
            str(tmp_path / "cli"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout)["status"] == "draft_not_admitted"
    missing = subprocess.run(
        [sys.executable, "-m", "principia_asd.cli", "prepare", "--spec", str(path)],
        capture_output=True,
        text=True,
    )
    assert missing.returncode == 2 and "--settings" in missing.stderr
    assert Path(root).is_dir()


def test_replay_refuses_changed_preparation_runtime_before_writing(tmp_path):
    root, _, recipe = permeation_recipe(tmp_path)
    path = tmp_path / "recipe.json"
    write_json(path, recipe)
    out = tmp_path / "original"
    prepare(path, root, out)
    environment = read_json(out / "preprocessing/environment.json")
    environment["module_hashes"]["principia_asd.catalog.splits"] = "changed"
    changed = tmp_path / "changed-environment.json"
    write_json(changed, environment)
    with pytest.raises(ValueError, match="runtime differs"):
        prepare(path, root, tmp_path / "replay", expected_environment=changed)
    assert not (tmp_path / "replay").exists()


def test_workbook_size_limit_is_checked_before_decoding(tmp_path):
    _, path, _ = permeation_recipe(tmp_path)
    with pytest.raises(ValueError, match="oversized"):
        numeric_sheet(path, "0.5 to 1 mA_cm2", max_bytes=30)


def test_verification_wrapper_cannot_create_inside_frozen_roots(tmp_path):
    from scripts.verify_native_reconstruction import verify

    source, data = tmp_path / "source", tmp_path / "data"
    for root in (source, data):
        root.mkdir()
        candidate = root / "new-draft"
        with pytest.raises(ValueError, match="outside"):
            verify(tmp_path, source, data, candidate, Path(sys.executable))
        assert not candidate.exists()
