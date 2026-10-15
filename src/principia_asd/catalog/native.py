"""Curator-only native reconstruction. No reference states, fitting or provider calls.

Raw public acquisitions can contain historically held-out measurements. This is
not an agent data reader: outputs omit test responses and do not admit a scenario.
"""

from __future__ import annotations

import csv
import hashlib
import importlib
import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

import numpy as np
import scipy

from ..io import contained, file_sha, read_csv, read_json, sha, write_csv, write_json
from .splits import check_chronology, check_units

VERSION = "native-reconstruction/1"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def identity(case, kind, value):
    """Preserve the historical migration's identities, including its JSON spacing."""
    raw = json.dumps([case, kind, str(value)], sort_keys=True, allow_nan=False).encode()
    return kind + "-" + hashlib.sha256(raw).hexdigest()[:24]


def _xml(raw):
    if b"\x00" in raw or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("XML declarations are not supported")
    return ET.fromstring(raw)


def numeric_sheet(path, name, *, max_bytes=10_000_000):
    """Read stored A/B numeric cells, retaining source rows; never evaluate formulas."""
    with zipfile.ZipFile(path) as archive:
        items = archive.infolist()
        names = [a.filename for a in items]
        if len(names) != len(set(names)) or sum(a.file_size for a in items) > max_bytes:
            raise ValueError("Duplicate or oversized XLSX members")
        if any(PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts for n in names):
            raise ValueError("Unsafe XLSX member path")
        workbook = _xml(archive.read("xl/workbook.xml"))
        sheets = [s for s in workbook.findall(f"{NS}sheets/{NS}sheet") if s.get("name") == name]
        if len(sheets) != 1:
            raise ValueError("Missing or ambiguous worksheet")
        links = _xml(archive.read("xl/_rels/workbook.xml.rels"))
        matches = [r for r in links if r.get("Id") == sheets[0].get(REL + "id")]
        if len(matches) != 1 or matches[0].get("TargetMode") == "External":
            raise ValueError("Unresolved or external worksheet")
        target = PurePosixPath(matches[0].get("Target", ""))
        if target.is_absolute() or ".." in target.parts:
            raise ValueError("Unsafe worksheet relationship")
        sheet = _xml(archive.read("xl/" + str(target)))
        strings = []
        if "xl/sharedStrings.xml" in names:
            strings = [
                "".join(t.text or "" for t in item.iter(NS + "t"))
                for item in _xml(archive.read("xl/sharedStrings.xml")).findall(NS + "si")
            ]
        rows, headers, excluded, seen = [], {}, [], set()
        for record in sheet.findall(f"{NS}sheetData/{NS}row"):
            row_id = int(record.attrib["r"])
            if row_id in seen or row_id < 1:
                raise ValueError("Duplicate or invalid source row")
            seen.add(row_id)
            cells = {}
            for cell in record.findall(NS + "c"):
                address = cell.get("r", "")
                if not re.fullmatch(r"[AB][1-9][0-9]*", address):
                    continue
                if int(address[1:]) != row_id or address[0] in cells:
                    raise ValueError("Ambiguous source cell")
                if cell.find(NS + "f") is not None:
                    raise ValueError("Formula or hidden fitted state in measurement cells")
                kind = cell.get("t", "n")
                value = cell.findtext(NS + "v")
                if kind == "s":
                    value = strings[int(value)]
                elif kind == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(NS + "t"))
                elif kind not in {"n", "str"}:
                    raise ValueError("Unsupported measurement cell type")
                cells[address[0]] = value
            if row_id == 1:
                headers = cells
            try:
                x, y = float(cells.get("A")), float(cells.get("B"))
            except (ValueError, TypeError):
                excluded.append(row_id)
                continue
            if not math.isfinite(x) or not math.isfinite(y):
                excluded.append(row_id)
                continue
            rows.append((row_id, x, y))
        rows.sort()
        if len(rows) < 20 or any(b[1] <= a[1] for a, b in zip(rows, rows[1:], strict=False)):
            raise ValueError("Invalid or nonmonotone acquisition clock")
        if headers != {"A": "Time, s", "B": "Current, μA"}:
            raise ValueError("Unexpected source measurement units")
        return rows, {"sheet": name, "headers": headers, "excluded_nonnumeric_rows": excluded}


def _row(case, label, group, split, values, response, anchor):
    result = {
        "sample_id": identity(case, "sample", label),
        "group": identity(case, "group", group),
        **values,
    }
    if split != "test":
        result["target"] = float(response)
    lineage = {"sample_id": result["sample_id"], "split": split, **anchor}
    return result, lineage


def _permeation(recipe, source_root):
    (asset,) = [a for a in recipe["assets"] if a["role"] == "permeation_workbook"]
    parts, lineage, diagnostics = {p: [] for p in ("train", "dev", "test")}, [], []
    for j, name in enumerate(["0.5 to 1 mA_cm2", "5 to 10 mA_cm2"]):
        rows, summary = numeric_sheet(contained(source_root, asset["path"]), name)
        diagnostics.append(summary)
        offset = float(np.mean([r[2] for r in rows[:3]]))
        origin = rows[2][1]
        for k in range(3, len(rows)):
            source_row, time, response = rows[k]
            block = min(4, int((k - 3) * 5 / (len(rows) - 3)))
            split = "train" if block < 3 else "dev" if block == 3 else "test"
            values = {
                "t": time - origin,
                "offset": offset,
                "drive": 0.5 if j == 0 else 5.0,
                "high": float(j),
            }
            row, source = _row(
                recipe["scenario_id"],
                f"trace-{j}-row-{source_row}",
                f"trace-{j}-block-{block}",
                split,
                values,
                response,
                {
                    "source": asset["path"],
                    "sheet": name,
                    "row": source_row,
                    "measurement_columns": ["A", "B"],
                    "calibration_rows": [r[0] for r in rows[:3]],
                    "time_origin_row": rows[2][0],
                    "stream": j,
                    "temporal_block": block,
                },
            )
            parts[split].append(row)
            lineage.append(source)
    checks = check_chronology(parts, time_column="t", stream_columns=("high", "drive"))
    return parts, lineage, {"split_check": checks, "sources": diagnostics}


def _xrr(recipe, source_root):
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    for asset in recipe["assets"]:
        if asset["role"] != "xrr_ras":
            continue
        path = contained(source_root, asset["path"])
        lines = path.read_text(errors="strict").splitlines()
        if lines.count("*RAS_INT_START") != 1 or lines.count("*RAS_INT_END") != 1:
            raise ValueError("Ambiguous RAS measurement block")
        begin, end = lines.index("*RAS_INT_START"), lines.index("*RAS_INT_END")
        if end <= begin:
            raise ValueError("Invalid RAS measurement block")
        for header in [
            '*MEAS_SCAN_AXIS_X "TwoThetaOmega"',
            '*MEAS_SCAN_UNIT_X "deg"',
            '*MEAS_SCAN_UNIT_Y "counts"',
            '*HW_XG_WAVE_LENGTH_ALPHA1 "1.540593"',
        ]:
            if header not in lines[:begin]:
                raise ValueError("Unexpected RAS axis, wavelength or units")
        native_lines = lines[begin + 1 : end]
        if any(len(line.split()) != 3 or "#" in line for line in native_lines):
            raise ValueError("RAS row shape would invalidate source-line provenance")
        array = np.loadtxt(io.StringIO("\n".join(native_lines)), ndmin=2)
        if array.shape[1] != 3 or not np.all(np.isfinite(array)) or not np.all(array[:, 2] == 1):
            raise ValueError("Unresolved RAS values or correction factors")
        if not np.all(np.diff(array[:, 0]) > 0):
            raise ValueError("Nonmonotone RAS angles")
        cal = np.flatnonzero(abs(array[:, 0] - 1.0) <= 0.00801)
        if not len(cal):
            raise ValueError("Missing permitted calibration band")
        q = 4 * np.pi * np.sin(np.deg2rad(array[:, 0] / 2)) / 1.540593
        offset, q0 = float(np.mean(array[cal, 1])), float(np.mean(q[cal]))
        if offset <= 0:
            raise ValueError("Nonpositive calibration intensity")
        wafer, position = int(asset["wafer"]), str(asset["position"])
        tokens = path.name.split("-")
        if not 1 <= wafer <= 12 or int(tokens[3]) != wafer or tokens[4] != position:
            raise ValueError("Registered source wafer identity mismatch")
        batch = (wafer - 1) // 3 + 1
        split = "train" if batch < 3 else "dev" if batch == 3 else "test"
        group = f"wafer-{wafer:02}"
        units[identity(recipe["scenario_id"], "group", group)] = f"deposition-{batch}"
        for k in range(0, len(array), 10):
            if not 1.4 <= array[k, 0] <= 4.8:
                continue
            line = begin + k + 2
            row, source = _row(
                recipe["scenario_id"],
                path.stem + f"-line-{line}",
                group,
                split,
                {"q": float(q[k]), "q0": q0, "I0": offset, "outer": float(position != "105")},
                array[k, 1],
                {
                    "source": asset["path"],
                    "line": line,
                    "measurement_columns": [1, 2],
                    "calibration_lines": [int(begin + x + 2) for x in cal],
                    "wafer": wafer,
                    "deposition_batch": batch,
                    "position": position,
                },
            )
            parts[split].append(row)
            lineage.append(source)
    return parts, lineage, {"split_check": check_units(parts, units)}


def _registered_groups(recipe, groups):
    assignments = recipe["group_assignments"]
    if set(assignments) != set(groups) or set(assignments.values()) != {"train", "dev", "test"}:
        raise ValueError("Incomplete or unknown registered independent-unit assignments")
    return assignments


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON source field or checkpoint")
        result[key] = value
    return result


def _gemstones(recipe, source_root):
    (asset,) = [a for a in recipe["assets"] if a["role"] == "training_histories"]
    path = contained(source_root, asset["path"])
    # Fixed acquisition scaling, corroborated by the registered extraction source.
    tokens_per_step = 2048 * 2048
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    histories, skipped, seen = [], [], set()
    with path.open() as stream:
        for line, raw in enumerate(stream, 1):
            record = json.loads(raw, object_pairs_hook=_unique_object)
            if type(record["pretrain"]) is not bool or type(record["cooldown"]) is not bool:
                raise ValueError("Ambiguous training-stage flags")
            if not (record["pretrain"] and not record["cooldown"]):
                skipped.append(line)
                continue
            group = record["model_id"]
            width, depth, params = (record[k] for k in ("width", "depth", "params"))
            if any(type(v) is not int or v <= 0 for v in (width, depth, params)):
                raise ValueError("Invalid architecture metadata")
            if group != f"{width}x{depth}" or group in seen:
                raise ValueError("Ambiguous or repeated architecture identity")
            seen.add(group)
            history = record["val_loss_by_optimiser_step"]
            if not isinstance(history, dict) or not history:
                raise ValueError("Missing validation measurements")
            sequence, excluded = [], []
            for key, value in history.items():
                if not re.fullmatch(r"0|[1-9][0-9]*", key):
                    raise ValueError("Noncanonical optimizer-step identity")
                # Preserve the inherited missing-observation cohort; do not impute it.
                if value is None:
                    excluded.append(key)
                    continue
                if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
                    raise ValueError("Invalid stored validation loss")
                sequence.append((int(key), float(value)))
            sequence.sort()
            early = [(k, y) for k, y in sequence if 0 < k * tokens_per_step <= 10e9]
            anchor = [(k, y) for k, y in sequence if 0 < k * tokens_per_step <= 20e9]
            if not early or not anchor or early[-1][0] >= anchor[-1][0]:
                raise ValueError("Missing distinct pre-forecast calibration checkpoints")
            forecasts = [(k, y) for k, y in sequence if 20e9 < k * tokens_per_step <= 100e9]
            if not forecasts:
                raise ValueError("No forecast observations for registered architecture")
            histories.append(
                (line, group, width, depth, params, early[-1], anchor[-1], forecasts, excluded)
            )
    assignments = _registered_groups(recipe, seen)
    summaries = []
    for line, group, width, depth, params, (k1, y1), (k0, y0), forecasts, excluded in histories:
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        summaries.append(
            {
                "line": line,
                "architecture": group,
                "excluded_missing_steps": excluded,
                "early_step": k1,
                "anchor_step": k0,
                "forecast_rows": len(forecasts),
            }
        )
        for step, response in forecasts:
            row, source = _row(
                recipe["scenario_id"],
                f"{group}|hot|step={step}",
                group,
                split,
                {
                    "tokens_B": step * tokens_per_step / 1e9,
                    "anchor_tokens_B": k0 * tokens_per_step / 1e9,
                    "early_tokens_B": k1 * tokens_per_step / 1e9,
                    "anchor_loss": y0,
                    "early_loss": y1,
                    "params_B": params / 1e9,
                    "width": float(width),
                    "depth": float(depth),
                },
                response,
                {
                    "source": asset["path"],
                    "line": line,
                    "architecture": group,
                    "response_path": f"val_loss_by_optimiser_step/{step}",
                    "calibration_paths": [f"val_loss_by_optimiser_step/{k}" for k in (k1, k0)],
                    "tokens_per_optimizer_step": tokens_per_step,
                    "permitted_calibration_precedes_response": k1 < k0 < step,
                },
            )
            parts[split].append(row)
            lineage.append(source)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "histories": summaries,
            "excluded_non_hot_source_lines": skipped,
            "calibration_scope": "Observed checkpoints at or before 10B and 20B tokens; not uncalibrated forecasting",
        },
    )


def _fet(recipe, source_root):
    (asset,) = [a for a in recipe["assets"] if a["role"] == "fet_sweeps"]
    path = contained(source_root, asset["path"])
    with path.open(newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader)
        if header != recipe["source_columns"] or header != [f"wave{i}" for i in range(len(header))]:
            raise ValueError("Unexpected or ambiguous FET measurement columns")
        values = []
        for line, row in enumerate(reader, 2):
            if len(row) != len(header):
                raise ValueError("Ragged FET source row")
            try:
                numbers = [float(v) for v in row]
            except ValueError as exc:
                raise ValueError("Non-numeric FET measurement or formula") from exc
            if not all(math.isfinite(v) for v in numbers):
                raise ValueError("Nonfinite FET measurement")
            values.append((line, numbers))
    if len(values) < 4 or any(b[1][0] <= a[1][0] for a, b in zip(values, values[1:], strict=False)):
        raise ValueError("Nonmonotone or repeated gate-voltage coordinate")
    calibration = []
    for anchor in [-20, 0, 20]:
        matched = [(line, nums) for line, nums in values if abs(nums[0] - anchor) <= 1e-10]
        if len(matched) != 1:
            raise ValueError("Missing or ambiguous FET calibration anchor")
        calibration.append(matched[0])
    if values[0][1][0] < -20 or values[-1][1][0] > 20:
        raise ValueError("FET observation outside registered calibrated domain")
    cal_rows = [line for line, _ in calibration]
    groups = {f"device-{j:02d}" for j in range(1, len(header))}
    assignments = _registered_groups(recipe, groups)
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    for j in range(1, len(header)):
        group = f"device-{j:02d}"
        split = assignments[group]
        # Units are declared in the source contract, not self-describing CSV headers.
        cal = [float(nums[j] * 1e6) for _, nums in calibration]
        units[identity(recipe["scenario_id"], "group", group)] = header[j]
        for line, nums in values:
            if line in cal_rows:
                continue
            row, source = _row(
                recipe["scenario_id"],
                f"{group}:row-{line}",
                group,
                split,
                {
                    "gate_V": nums[0],
                    "cal_minus20_uA": cal[0],
                    "cal_zero_uA": cal[1],
                    "cal_plus20_uA": cal[2],
                },
                nums[j] * 1e6,
                {
                    "source": asset["path"],
                    "row": line,
                    "input_column": header[0],
                    "response_column": header[j],
                    "source_device_group": group,
                    "calibration_rows": cal_rows,
                    "calibration_column": header[j],
                    "current_conversion": "stored A multiplied by 1e6 -> uA",
                    "calibration_scope": "Three disclosed same-column measurements, including both sweep endpoints",
                },
            )
            parts[split].append(row)
            lineage.append(source)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "calibration_rows_excluded_from_response_cohort": cal_rows,
            "independence_scope": "Complete source columns; no fabrication-batch or independently measured specimen identity is established",
            "units_scope": "Inherited declared V/A units; source wave headers do not independently encode units",
        },
    )


def reconstruct(recipe, source_root):
    from .afm import reconstruct_afm
    from .battery import reconstruct_battery
    from .boiling import reconstruct_boiling
    from .choices import reconstruct_choices
    from .comcat import reconstruct_comcat
    from .compiler import reconstruct_compiler
    from .coral import reconstruct_coral
    from .cpap import reconstruct_cpap
    from .crowd import reconstruct_crowd
    from .curves import reconstruct_kinase, reconstruct_neuronal
    from .fermentation import reconstruct_fermentation
    from .finger_friction import reconstruct_finger_friction
    from .fracture import reconstruct_fracture
    from .games import reconstruct_games
    from .gwosc import reconstruct_gwosc
    from .levitation import reconstruct_levitation
    from .lubricants import reconstruct_lubricants
    from .memristor import reconstruct_memristor
    from .microscopy import reconstruct_microscopy
    from .microwave import reconstruct_microwave
    from .nhtsa import reconstruct_nhtsa
    from .piaac import reconstruct_piaac
    from .ppg import reconstruct_ppg
    from .rydberg import reconstruct_rydberg
    from .screw import reconstruct_screw
    from .shed import reconstruct_shed
    from .slag import reconstruct_slag
    from .storm import reconstruct_storm
    from .tomato import reconstruct_tomato
    from .xas import reconstruct_xas
    from .yeast import reconstruct_yeast
    from .zeolite import reconstruct_zeolite

    source_root = Path(source_root).resolve()
    if recipe["schema_version"] != VERSION:
        raise ValueError("Unsupported reconstruction recipe")
    parsers = {
        "hafnia-xrr-v1": ("P100-012", _xrr),
        "hydrogen-permeation-v1": ("P100-062", _permeation),
        "gemstones-hot-trajectories-v1": ("P100-043", _gemstones),
        "fet-calibrated-sweeps-v1": ("P100-051", _fet),
        "microfracture-geometry-traces-v1": ("P100-054", reconstruct_fracture),
        "src-kinase-calibrated-curves-v1": ("P100-074", reconstruct_kinase),
        "neuronal-prefix-curves-v1": ("P100-076", reconstruct_neuronal),
        "fermentation-historical-clock-audit-v1": ("P100-086", reconstruct_fermentation),
        "threshold-public-goods-session1-v1": ("P100-087", reconstruct_games),
        "risk-choice-identity-order-audit-v1": ("P100-089", reconstruct_choices),
        "crowd-prefix-xy-conditions-v1": ("P100-090", reconstruct_crowd),
        "levitation-raw-delay-traces-v1": ("P100-068", reconstruct_levitation),
        "comcat-origin-quality-clusters-v1": ("P100-017", reconstruct_comcat),
        "rydberg-ion-source-grid-v1": ("P100-006", reconstruct_rydberg),
        "basytec-gitt-rest-prefix-v1": ("P100-049", reconstruct_battery),
        "perovskite-forming-traces-v1": ("P100-022", reconstruct_memristor),
        "hbn-calibrated-formulation-curves-v1": ("P100-030", reconstruct_lubricants),
        "finger-friction-participant-summary-v1": ("P100-023", reconstruct_finger_friction),
        "zeolite-fixed-prefix-reactors-v1": ("P100-026", reconstruct_zeolite),
        "kth-boiling-pressure-properties-v1": ("P100-027", reconstruct_boiling),
        "cpap-raw-adc-delay-traces-v1": ("P100-032", reconstruct_cpap),
        "cellulose-afm-calibrated-retraction-v1": ("P100-084", reconstruct_afm),
        "slag-mixture-penetration-traces-v1": ("P100-055", reconstruct_slag),
        "lfp-native-calibrated-xanes-v1": ("P100-025", reconstruct_xas),
        "microwave-native-usb-matrices-v1": ("P100-028", reconstruct_microwave),
        "ppg-native-waveform-features-v1": ("P100-033", reconstruct_ppg),
        "microscopy-native-bz-stencil-v1": ("P100-070", reconstruct_microscopy),
        "gwosc-native-causal-spectral-windows-v1": ("P100-003", reconstruct_gwosc),
        "coral-native-ssta-stencil-v1": ("P100-020", reconstruct_coral),
        "nhtsa-historical-counts-record-audit-v1": ("P100-019", reconstruct_nhtsa),
        "piaac-native-respondent-deciles-v1": ("P100-039", reconstruct_piaac),
        "shed-native-state-respondent-custody-v1": ("P100-015", reconstruct_shed),
        "noaa-storm-tornado-reports-v1": ("P100-018", reconstruct_storm),
        "tomato-stored-phenotype-custody-v1": ("P100-036", reconstruct_tomato),
        "yeast-native-calibrated-qpcr-v1": ("P100-072", reconstruct_yeast),
        "screw-native-causal-torque-prefix-v1": ("P100-053", reconstruct_screw),
        "benchpress-recorded-pilot-timings-v1": ("P100-031", reconstruct_compiler),
    }
    case, parser = parsers[recipe["parser"]]
    if case != recipe["scenario_id"]:
        raise ValueError("Recipe/scenario identity mismatch")
    assets = recipe["assets"]
    if not assets or len({a["path"] for a in assets}) != len(assets):
        raise ValueError("Missing or duplicate registered source assets")
    for asset in assets:
        path = contained(source_root, asset["path"])
        if path.stat().st_size != asset["bytes"] or file_sha(path) != asset["sha256"]:
            raise ValueError("Registered source hash or size mismatch: " + asset["path"])
    parts, lineage, checks = parser(recipe, source_root)
    ids = [r["sample_id"] for rows in parts.values() for r in rows]
    if len(ids) != len(set(ids)) or not all(parts.values()) or not checks["split_check"]["valid"]:
        raise ValueError("Invalid source identities or scientific split")
    if any("target" in row for row in parts["test"]):
        raise ValueError("Test response escaped curator boundary")
    for rows in parts.values():
        for row in rows:
            if any(not math.isfinite(v) for k, v in row.items() if k not in {"sample_id", "group"}):
                raise ValueError("Nonfinite prepared measurement")
    return parts, lineage, checks


def compare_public(parts, scenario, *, rel_tol=1e-12, abs_tol=1e-12):
    """Parity with development and permitted test inputs, never evaluator targets."""
    task = read_json(scenario / "task-contracts/task-001.json")
    recorded = {
        p: read_csv(contained(scenario, rel))
        for p, rel in task["split"].items()
        if p in {"train", "dev", "test"}
    }
    results = {}
    for name, splits in {"development_union": ["train", "dev"], "test_inputs": ["test"]}.items():
        a = [row for p in splits for row in parts[p]]
        b = [row for p in splits for row in recorded[p]]
        actual, expected = {r["sample_id"]: r for r in a}, {r["sample_id"]: r for r in b}
        if len(actual) != len(a) or len(expected) != len(b) or actual.keys() != expected.keys():
            raise ValueError("Reconstruction cohort identity mismatch")
        maximum, differences = 0.0, 0
        for sid, row in actual.items():
            prior = expected[sid]
            if row.keys() != prior.keys():
                raise ValueError("Reconstruction measurement fields mismatch")
            for key, value in row.items():
                if key in {"sample_id", "group"}:
                    if value != prior[key]:
                        raise ValueError("Reconstruction group mismatch")
                else:
                    if not math.isfinite(float(prior[key])) or not math.isclose(
                        value, prior[key], rel_tol=rel_tol, abs_tol=abs_tol
                    ):
                        raise ValueError("Reconstructed measurement differs: " + key)
                    maximum = max(maximum, abs(value - prior[key]))
                    differences += int(value != prior[key])
        results[name] = {
            "rows": len(a),
            "exact_sample_and_group_coverage": True,
            "max_absolute_numeric_difference": maximum,
            "nonidentical_float_values": differences,
        }
    return {
        "status": "passed",
        "relative_tolerance": rel_tol,
        "absolute_tolerance": abs_tol,
        "cohorts": results,
        "partition_membership": {
            p: {
                "unchanged": {r["sample_id"] for r in parts[p]}
                == {r["sample_id"] for r in recorded[p]},
                "reconstructed_rows": len(parts[p]),
                "historical_rows": len(recorded[p]),
            }
            for p in ("train", "dev", "test")
        },
        "evaluator_targets_accessed": False,
    }


def runtime_binding(parser=None):
    names = [
        "principia_asd.catalog.native",
        "principia_asd.catalog.fracture",
        "principia_asd.catalog.curves",
        "principia_asd.catalog.fermentation",
        "principia_asd.catalog.games",
        "principia_asd.catalog.choices",
        "principia_asd.catalog.crowd",
        "principia_asd.catalog.levitation",
        "principia_asd.catalog.comcat",
        "principia_asd.catalog.compiler",
        "principia_asd.catalog.screw",
        "principia_asd.catalog.yeast",
        "principia_asd.catalog.ppg",
        "principia_asd.catalog.tomato",
        "principia_asd.catalog.storm",
        "principia_asd.catalog.gwosc",
        "principia_asd.catalog.coral",
        "principia_asd.catalog.nhtsa",
        "principia_asd.catalog.piaac",
        "principia_asd.catalog.shed",
        "principia_asd.catalog.rydberg",
        "principia_asd.catalog.battery",
        "principia_asd.catalog.memristor",
        "principia_asd.catalog.lubricants",
        "principia_asd.catalog.finger_friction",
        "principia_asd.catalog.zeolite",
        "principia_asd.catalog.boiling",
        "principia_asd.catalog.cpap",
        "principia_asd.catalog.afm",
        "principia_asd.catalog.slag",
        "principia_asd.catalog.xas",
        "principia_asd.catalog.microwave",
        "principia_asd.catalog.microscopy",
        "principia_asd.catalog.splits",
        "principia_asd.io",
    ]
    extra = {}
    if parser in {
        "microwave-native-usb-matrices-v1",
        "gwosc-native-causal-spectral-windows-v1",
        "coral-native-ssta-stencil-v1",
    }:
        from .microwave import decoder_binding

        extra["native_decoder"] = decoder_binding()
    return {
        **extra,
        "python": ">=3.11",
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "reader_version": VERSION,
        "module_hashes": {
            name: file_sha(Path(importlib.import_module(name).__file__)) for name in names
        },
        "learned_transformations": [],
    }


def prepare(
    recipe_path, source_root, output_root, *, compare_scenario=None, expected_environment=None
):
    recipe = read_json(Path(recipe_path))
    environment = runtime_binding(recipe["parser"])
    if expected_environment and read_json(Path(expected_environment)) != environment:
        raise ValueError("Reconstruction runtime differs from the frozen preparation environment")
    recipe_path, source_root, output_root = (
        Path(x).resolve() for x in (recipe_path, source_root, output_root)
    )
    if output_root.is_relative_to(source_root) or any(
        (p / "EDITION.json").exists() for p in [output_root, *output_root.parents]
    ):
        raise ValueError("Output must be outside source and frozen edition roots")
    if output_root.exists():
        raise FileExistsError("Reconstruction output is immutable; choose a new identity")
    recipe = read_json(recipe_path)
    parts, lineage, checks = reconstruct(recipe, source_root)
    parity = None
    if compare_scenario:
        scenario = Path(compare_scenario).resolve()
        task = read_json(scenario / "task-contracts/task-001.json")
        if sha(task) != recipe["historical_contract_sha256"]:
            raise ValueError("Historical parity contract mismatch")
        parity = compare_public(parts, scenario)
    output_root.mkdir(parents=True, exist_ok=False)
    for split, rows in parts.items():
        name = "test_inputs" if split == "test" else split
        write_csv(output_root / f"public/{name}.csv.gz", rows, list(rows[0]))
    write_json(output_root / "preprocessing/recipe.json", recipe, immutable=True)
    write_json(output_root / "preprocessing/lineage.json", lineage, immutable=True)
    write_json(output_root / "preprocessing/environment.json", environment, immutable=True)
    (output_root / "preprocessing/prepare.py").write_text(
        '"""Rebuild this draft into a NEW output directory from its registered raw sources."""\n'
        "import argparse\nfrom pathlib import Path\nfrom principia_asd.catalog.native import prepare\n"
        'p = argparse.ArgumentParser()\np.add_argument("--source-root", required=True)\n'
        'p.add_argument("--output-root", required=True)\na = p.parse_args()\n'
        'prepare(Path(__file__).with_name("recipe.json"), a.source_root, a.output_root, '
        'expected_environment=Path(__file__).with_name("environment.json"))\n'
    )
    files = {
        str(p.relative_to(output_root)): file_sha(p)
        for p in sorted(output_root.rglob("*"))
        if p.is_file()
    }
    receipt = {
        "schema_version": VERSION,
        "scenario_id": recipe["scenario_id"],
        "status": "draft_not_admitted",
        "recipe_sha256": file_sha(recipe_path),
        "reader_source_sha256": environment["module_hashes"]["principia_asd.catalog.native"],
        "runtime_binding_sha256": sha(environment),
        "checks": checks,
        "rows": {p: len(rows) for p, rows in parts.items()},
        "historical_public_parity": parity,
        "files": files,
        "api_calls": 0,
        "fitting_attempts": 0,
        "test_targets_exported": False,
        "evaluator_vault_accessed": False,
        "scope": "Curator reconstruction from raw acquisitions; no approval of rights, scientific admission or independent evidence",
    }
    write_json(output_root / "reconstruction.json", receipt, immutable=True)
    return receipt
