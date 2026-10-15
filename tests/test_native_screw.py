import copy
import csv
import io
import json
import zipfile
from datetime import datetime, timedelta

import numpy as np
import pytest

from principia_asd.catalog.native import reconstruct
from principia_asd.catalog.screw import (
    FIELDS,
    INPUT_UNITS,
    PARSER,
    Unavailable,
    assignments,
    decode,
    labels,
    measurements,
    reconstruct_screw,
)
from principia_asd.io import file_sha


def record(op):
    def step(name, x, t):
        return {
            "name": name,
            "graph": {
                "angle values": x.tolist(),
                "torque values": (0.2 + 0.0001 * x).tolist(),
                "time values": t.tolist(),
            },
        }

    return {
        "format": "channel",
        "cycle": int(op["run_id"]),
        "id code": op["workpiece_id"],
        "date": op["workpiece_date"],
        "result": op["workpiece_result"],
        "torque unit": "Nm",
        "MCE factor": 1,
        "MCE": [{"Transducer function": "primary", "measuring": "direct", "factor": 1}],
        "total time": "2",
        "tightening steps": [
            step("Finding", np.arange(0.0, 101.0, 5.0), np.arange(21) * 0.001),
            step("Thread forming", np.arange(100.0, 1501.0, 10.0), 0.1 + np.arange(141) * 0.001),
        ],
    }


@pytest.fixture
def panel():
    rows, docs = [], {}
    for w in range(5):
        for side in ("left", "right"):
            for usage in range(25):
                rid = 1000 + len(rows)
                op = dict(
                    zip(
                        FIELDS,
                        [
                            str(rid),
                            f"Ch_{rid:012d}.json",
                            "001_control-group",
                            f"{30000000000000 + w}",
                            str(
                                datetime(2023, 1, 1)
                                + timedelta(seconds=100 * usage + (side == "right") * 5)
                            ),
                            str(usage),
                            "OK",
                            side,
                            "normal",
                            "0",
                        ],
                        strict=True,
                    )
                )
                rows.append(op)
                docs[op["file_name"]] = record(op)
    return rows, docs


def csv_bytes(rows):
    f = io.StringIO()
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)
    return f.getvalue().encode()


def fixture(tmp_path, panel):
    rows, docs = panel
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("labels.csv", csv_bytes(rows))
        z.writestr("README.md", "fixture")
        for r in rows:
            z.writestr(
                "json/" + r["class_value"] + "/" + r["file_name"], json.dumps(docs[r["file_name"]])
            )
    meta = tmp_path / "source.json"
    meta.write_text(json.dumps({"source_version": "16031381", "license_or_terms": "cc-by-4.0"}))
    return {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-053",
        "parser": PARSER,
        "assets": [
            {"path": f.name, "bytes": f.stat().st_size, "sha256": file_sha(f), "role": role}
            for f, role in [(path, "screw_archive"), (meta, "source_metadata")]
        ],
        "input_units": INPUT_UNITS,
        "output_units": "Nm",
        "group_assignments": assignments("P100-053", labels(csv_bytes(rows))),
    }


def test_complete_panel_causal_history_and_exact_groups(tmp_path, panel):
    recipe = fixture(tmp_path, panel)
    parts, lineage, c = reconstruct(recipe, tmp_path)
    assert {k: len(v) for k, v in parts.items()} == {"train": 150, "dev": 50, "test": 50}
    assert c["screw_validation"]["history_links"] == 240
    assert c["screw_validation"]["minimum_conservative_history_margin_s"] > 90
    assert not any("target" in r for r in parts["test"])
    assert all(r["history_gap"] in (0, 1) for rows in parts.values() for r in rows)
    assert sum(a["previous_labels_row"] is None for a in lineage) == 10
    assert c["split_check"]["valid"]


@pytest.mark.parametrize(
    "change", ["duplicate", "missing", "usage", "location", "date", "class", "filename"]
)
def test_inventory_guards(panel, change):
    rows, _ = panel
    if change == "duplicate":
        rows[1] = copy.deepcopy(rows[0])
    elif change == "missing":
        rows.pop()
    elif change == "usage":
        rows[0]["workpiece_usage"] = "25"
    elif change == "location":
        rows[0]["workpiece_location"] = "middle"
    elif change == "date":
        rows[0]["workpiece_date"] = "2023-invalid"
    elif change == "class":
        rows[0]["class_value"] = "201_other"
    else:
        rows[0]["file_name"] = "../bad.json"
    with pytest.raises(ValueError):
        labels(csv_bytes(rows))


@pytest.mark.parametrize(
    "change", ["unit", "identity", "calibration", "step", "clock", "shape", "nan", "bool"]
)
def test_native_guards(panel, change):
    rows, docs = panel
    r = rows[0]
    d = docs[r["file_name"]]
    g = d["tightening steps"][1]["graph"]
    if change == "unit":
        d["torque unit"] = "Nmm"
    elif change == "identity":
        d["cycle"] = 999
    elif change == "calibration":
        d["MCE"][0]["factor"] = 2
    elif change == "step":
        d["tightening steps"].append(copy.deepcopy(d["tightening steps"][0]))
    elif change == "clock":
        g["time values"][5] = 0
    elif change == "shape":
        g["torque values"].pop()
    elif change == "nan":
        g["torque values"][5] = float("nan")
    else:
        g["torque values"][5] = True
    with pytest.raises(ValueError):
        decode(json.dumps(d).encode(), r)


def test_sampled_trigger_and_future_torque_boundary(panel):
    rows, docs = panel
    r = rows[0]
    d = docs[r["file_name"]]
    a, *_ = decode(json.dumps(d).encode(), r)
    values, target, timing = measurements(a)
    a["Thread forming"][1, 26:] += 100
    revised, revised_target, _ = measurements(a)
    assert revised == values and revised_target != target
    assert timing["trigger_index"] == 25 and timing["target_end_index"] == 130


def test_nonforward_angle_does_not_advance_prefix(panel):
    rows, docs = panel
    r = rows[0]
    a, *_ = decode(json.dumps(docs[r["file_name"]]).encode(), r)
    a["Thread forming"][0, 10] = a["Thread forming"][0, 9]
    _, _, t = measurements(a)
    assert t["discarded_nonforward_samples"] == 1


@pytest.mark.parametrize("change", ["missing_step", "short_window", "sparse", "finding_future"])
def test_unavailable_and_future_finding(panel, change):
    rows, docs = panel
    r = rows[0]
    a, *_ = decode(json.dumps(docs[r["file_name"]]).encode(), r)
    if change == "missing_step":
        a.pop("Thread forming")
    elif change == "short_window":
        a["Thread forming"] = a["Thread forming"][:, :100]
    elif change == "sparse":
        a["Thread forming"] = a["Thread forming"][:, ::5]
    else:
        a["Finding"][2] += 2
    with pytest.raises(ValueError if change == "finding_future" else Unavailable):
        measurements(a)


def test_final_heldout_response_changes_no_inputs(tmp_path, panel):
    recipe = fixture(tmp_path, panel)
    before, _, _ = reconstruct_screw(recipe, tmp_path)
    rows, docs = panel
    for r in rows:
        if (
            recipe["group_assignments"][r["workpiece_id"]] == "test"
            and r["workpiece_usage"] == "24"
        ):
            g = docs[r["file_name"]]["tightening steps"][1]["graph"]
            g["torque values"][26:] = [4.0] * len(g["torque values"][26:])
    recipe = fixture(tmp_path, panel)
    after, _, _ = reconstruct_screw(recipe, tmp_path)
    assert before == after


def test_completed_prior_response_is_explicit_online_history(tmp_path, panel):
    recipe = fixture(tmp_path, panel)
    before, _, _ = reconstruct_screw(recipe, tmp_path)
    rows, docs = panel
    for r in rows:
        if (
            recipe["group_assignments"][r["workpiece_id"]] == "test"
            and r["workpiece_usage"] == "0"
            and r["workpiece_location"] == "left"
        ):
            g = docs[r["file_name"]]["tightening steps"][1]["graph"]
            g["torque values"][26:] = [4.0] * len(g["torque values"][26:])
    recipe = fixture(tmp_path, panel)
    after, _, _ = reconstruct_screw(recipe, tmp_path)
    assert before["train"] == after["train"] and before["dev"] == after["dev"]
    assert before["test"][0] == after["test"][0]
    assert before["test"][1]["prev_y"] != after["test"][1]["prev_y"]
    assert before["test"][1]["early"] == after["test"][1]["early"]
    assert before["test"][25:] == after["test"][25:]


def test_overlapping_history_refused(tmp_path, panel):
    rows, docs = panel
    rows[1]["workpiece_date"] = rows[0]["workpiece_date"]
    docs[rows[1]["file_name"]]["date"] = rows[0]["workpiece_date"]
    with pytest.raises(ValueError, match="Prior same-hole"):
        reconstruct_screw(fixture(tmp_path, panel), tmp_path)


def test_source_mutation_refused(tmp_path, panel):
    recipe = fixture(tmp_path, panel)
    (tmp_path / "source.zip").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, tmp_path)
