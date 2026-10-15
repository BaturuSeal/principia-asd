import copy
import json
import zipfile
from pathlib import Path

import pytest

from principia_asd.catalog.compiler import (
    INFO_KEYS,
    INPUT_UNITS,
    PARSER,
    SDKS,
    decode_report,
    family,
    member,
    original_assignments,
    reconstruct_compiler,
)
from principia_asd.catalog.native import reconstruct
from principia_asd.io import file_sha


@pytest.fixture
def reports():
    recipe = json.loads(Path("configs/preparation/P100-031.raw-v1.json").read_text())
    result = {}
    for sdk in SDKS:
        rows = []
        dumps = {"passed": {}, "failed": {}, "xfailed": {}, "skipped": {}}
        for idx, fn in enumerate(recipe["completed_circuits"][sdk]):
            full = f"{sdk}_gym/device_transpile/test_fixture.py::test[{fn}]"
            rows.append(
                {
                    "fullname": full,
                    "params": {"filename": fn},
                    "stats": {
                        "mean": 1.0,
                        "min": 0.5,
                        "max": 1.5,
                        "stddev": 0.5,
                        "rounds": 3,
                        "iterations": 1,
                        "total": 3.0,
                    },
                    "options": {"timer": "perf_counter"},
                    "extra_info": {
                        "input_num_qubits": 4,
                        "output_gate_count_2q": idx + 1,
                        "output_depth_2q": idx + 1,
                        "qasm_load_time": 0.01,
                    },
                }
            )
            dumps["passed"][full] = {}
        for fn in set(recipe["completed_circuits"]["qiskit"]) - set(
            recipe["completed_circuits"][sdk]
        ):
            state = "xfailed" if sdk == "tket" else "failed"
            dumps[state][f"{sdk}_gym/device_transpile/test_fixture.py::test[{fn}]"] = {}
        result[sdk] = {
            "version": "4.0.0",
            "benchmarks": rows,
            "commit_info": {"project": "benchpress", "dirty": False, "id": "a" * 40},
            "test_dumps": dumps,
            "test_status_counts": {k: len(v) for k, v in dumps.items()},
            "machine_info": {"cpu": {"brand_raw": "AMD Ryzen 9 7900 12-Core Processor"}},
            "datetime": "2024-08-01T00:00:00+00:00",
            INFO_KEYS[sdk]: {"test_version": "1"},
        }
    return result


def write_reports(tmp_path, reports):
    p = tmp_path / "source.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        for s, d in reports.items():
            z.writestr(member(s), json.dumps(d))
    return p


def make_recipe(tmp_path, reports):
    p = write_reports(tmp_path, reports)
    meta = tmp_path / "metadata.json"
    meta.write_text(
        json.dumps(
            {
                "id": 14977295,
                "doi": "10.5281/zenodo.14977295",
                "metadata": {"license": {"id": "cc-by-4.0"}},
            }
        )
    )
    circuits = {
        s: sorted(b["params"]["filename"] for b in d["benchmarks"]) for s, d in reports.items()
    }
    return {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-031",
        "parser": PARSER,
        "input_units": INPUT_UNITS.copy(),
        "output_units": "seconds",
        "completed_circuits": circuits,
        "group_assignments": original_assignments("P100-031", circuits["qiskit"]),
        "assets": [
            {"path": f.name, "role": role, "bytes": f.stat().st_size, "sha256": file_sha(f)}
            for f, role in [(p, "compiler_archive"), (meta, "source_metadata")]
        ],
    }


def test_full_cohort_and_missing_outcomes_preserved(tmp_path, reports):
    r = make_recipe(tmp_path, reports)
    parts, lineage, checks = reconstruct(r, tmp_path)
    assert {k: len(v) for k, v in parts.items()} == {"train": 78, "dev": 20, "test": 37}
    assert len(lineage) == 135 and checks["split_check"]["valid"]
    v = checks["compiler_validation"]
    assert v["matched_successful_pairs"] == 135 and v["pilot_unique_circuits"] == 50
    assert len(v["missing_pairs"]) == 15
    assert sum(x["status"] == "failed" for x in v["missing_pairs"]) == 12
    assert sum(x["status"] == "xfailed" for x in v["missing_pairs"]) == 3
    assert v["pilot_total_measured_round_seconds"] == 150
    assert all("target" not in x for x in parts["test"])
    assert len({x["sample_id"] for rows in parts.values() for x in rows}) == 135
    assert all(a["pilot_member"] == member("qiskit") for a in lineage)


@pytest.mark.parametrize(
    "name,result",
    [
        ("gf2^7_mult.qasm", "gf^_mult"),
        ("gf2^32_mult.qasm", "gf^_mult"),
        ("ham15-high.qasm", "ham-high"),
        ("tof_3.qasm", "tof"),
        ("W-state.qasm", "w-state"),
    ],
)
def test_exact_numeric_token_family_rule(name, result):
    assert family(name) == result


@pytest.mark.parametrize("name", ["../circuit.qasm", "/circuit.qasm", "bad.csv", "123.qasm"])
def test_unsafe_family_rejected(name):
    with pytest.raises(ValueError):
        family(name)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "name",
        "sdk",
        "count",
        "status",
        "timer",
        "total",
        "negative",
        "nan",
        "fractional_qubit",
        "dirty",
        "version",
    ],
)
def test_source_report_guards(reports, mutation):
    d = reports["qiskit"]
    b = d["benchmarks"][0]
    if mutation == "duplicate":
        d["benchmarks"][1] = copy.deepcopy(b)
    elif mutation == "name":
        b["params"]["filename"] = "different.qasm"
    elif mutation == "sdk":
        b["fullname"] = b["fullname"].replace("qiskit_gym", "tket_gym")
    elif mutation == "count":
        d["test_status_counts"]["passed"] += 1
    elif mutation == "status":
        d["test_dumps"]["failed"] = d["test_dumps"].pop("passed")
    elif mutation == "timer":
        b["options"]["timer"] = "unknown"
    elif mutation == "total":
        b["stats"]["total"] = 4
    elif mutation == "negative":
        b["stats"]["mean"] = -1
    elif mutation == "nan":
        b["stats"]["mean"] = float("nan")
    elif mutation == "fractional_qubit":
        b["extra_info"]["input_num_qubits"] = 4.5
    elif mutation == "dirty":
        d["commit_info"]["dirty"] = True
    else:
        d["version"] = "3"
    with pytest.raises((ValueError, KeyError)):
        decode_report(json.dumps(d).encode(), "qiskit")


def test_duplicate_json_keys_rejected():
    with pytest.raises(ValueError):
        decode_report(b'{"version":"4.0.0","version":"3.0"}', "qiskit")


def test_target_and_other_sdk_outputs_never_change_inputs(tmp_path, reports):
    r = make_recipe(tmp_path, reports)
    before = reconstruct_compiler(r, tmp_path)[0]
    for sdk in SDKS[1:]:
        for b in reports[sdk]["benchmarks"]:
            for key in ("mean", "min", "max", "stddev", "total"):
                b["stats"][key] *= 2
            b["extra_info"]["output_gate_count_2q"] = 999999
            b["extra_info"]["qasm_load_time"] = 999999
    write_reports(tmp_path, reports)
    after = reconstruct_compiler(r, tmp_path)[0]
    for s in before:
        for a, b in zip(before[s], after[s], strict=True):
            assert {k: v for k, v in a.items() if k != "target"} == {
                k: v for k, v in b.items() if k != "target"
            }
            if s != "test":
                assert b["target"] == 2 * a["target"]


def test_pilot_calibration_is_circuit_local(tmp_path, reports):
    r = make_recipe(tmp_path, reports)
    before = reconstruct_compiler(r, tmp_path)[0]
    b = reports["qiskit"]["benchmarks"][0]
    fn = b["params"]["filename"]
    for key in ("mean", "min", "max", "stddev", "total"):
        b["stats"][key] *= 2
    write_reports(tmp_path, reports)
    after = reconstruct_compiler(r, tmp_path)[0]
    changes = [(a, b) for s in before for a, b in zip(before[s], after[s], strict=True) if a != b]
    assert len(changes) == sum(
        any(x["params"]["filename"] == fn for x in reports[s]["benchmarks"]) for s in SDKS[1:]
    )
    assert all(
        b["pilot_seconds"] == 2 * a["pilot_seconds"]
        and {k: v for k, v in a.items() if k != "pilot_seconds"}
        == {k: v for k, v in b.items() if k != "pilot_seconds"}
        for a, b in changes
    )


@pytest.mark.parametrize("mutation", ["missing", "cpu", "qubits", "groups", "units", "unaccounted"])
def test_source_join_and_frozen_cohort_guards(tmp_path, reports, mutation):
    r = make_recipe(tmp_path, reports)
    if mutation == "missing":
        r["completed_circuits"]["staq"].pop()
    elif mutation == "cpu":
        reports["staq"]["machine_info"]["cpu"]["brand_raw"] = "different"
    elif mutation == "qubits":
        reports["staq"]["benchmarks"][0]["extra_info"]["input_num_qubits"] = 7
    elif mutation == "groups":
        r["group_assignments"][next(iter(r["group_assignments"]))] = "invalid"
    elif mutation == "units":
        r["input_units"]["pilot_seconds"] = "ms"
    else:
        d = reports["tket"]
        d["test_dumps"]["xfailed"] = {}
        d["test_status_counts"]["xfailed"] = 0
    write_reports(tmp_path, reports)
    with pytest.raises(ValueError):
        reconstruct_compiler(r, tmp_path)


def test_source_mutation_denied(tmp_path, reports):
    r = make_recipe(tmp_path, reports)
    reports["staq"]["benchmarks"][0]["extra_info"]["output_depth_2q"] = 999
    write_reports(tmp_path, reports)
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(r, tmp_path)
