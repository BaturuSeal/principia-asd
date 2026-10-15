"""Curator-only forming-branch reconstruction from stored XLSX measurements.

Workbook positions are source trace identities, not verified physical device IDs.
The frozen duplicate map is checked before use; responses never select new groups.
"""

import hashlib
import io
import json
import math
import re
from pathlib import PurePosixPath

import numpy as np

from ..io import contained, sha
from .fracture import NS, REL, bounded_zip
from .splits import check_units

MEMBERS = [("I", "dataset/Figure 3(a).xlsx"), ("Br", "dataset/Figure 3(d).xlsx")]


def column_number(label):
    number = 0
    for char in label:
        number = number * 26 + ord(char) - 64
    return number


def row_ranges(rows):
    ranges = []
    for row in rows:
        if ranges and row == ranges[-1][1] + 1:
            ranges[-1][1] = row
        else:
            ranges.append([row, row])
    return ranges


def stored_traces(raw, *, devices=50, max_rows=5000):
    """Read bounded stored pairs, reject formulas, preserve actual worksheet rows."""
    from .native import _xml

    if len(raw) > 2_000_000 or not 1 <= devices <= 50:
        raise ValueError("Oversized workbook or invalid device count")
    with bounded_zip(io.BytesIO(raw), max_bytes=6_000_000, max_member_bytes=5_000_000) as z:
        workbook = _xml(z.read("xl/workbook.xml"))
        sheets = workbook.findall(f"{NS}sheets/{NS}sheet")
        if len(sheets) != 1 or sheets[0].get("name") != "Sheet1":
            raise ValueError("Unexpected forming-sweep worksheet inventory")
        links = _xml(z.read("xl/_rels/workbook.xml.rels"))
        matches = [r for r in links if r.get("Id") == sheets[0].get(REL + "id")]
        if len(matches) != 1 or matches[0].get("TargetMode") == "External":
            raise ValueError("Unresolved or external forming-sweep worksheet")
        target = PurePosixPath(matches[0].get("Target", ""))
        if target.is_absolute() or ".." in target.parts:
            raise ValueError("Unsafe forming-sweep worksheet relationship")
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = [
                "".join(t.text or "" for t in item.iter(NS + "t"))
                for item in _xml(z.read("xl/sharedStrings.xml")).findall(NS + "si")
            ]
        traces, source_rows = [[] for _ in range(devices)], [[] for _ in range(devices)]
        missing, previous, markers = [[] for _ in range(devices)], 0, 0
        for row in _xml(z.read("xl/" + str(target))).findall(f"{NS}sheetData/{NS}row"):
            number = int(row.attrib["r"])
            if number != previous + 1 or number > max_rows:
                raise ValueError("Missing, reordered or excessive forming source row")
            previous = number
            values = {}
            for cell in row.findall(NS + "c"):
                match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", cell.get("r", ""))
                if not match:
                    raise ValueError("Invalid forming source cell address")
                col, cell_row = column_number(match[1]), int(match[2])
                if cell_row != number or col in values or not 1 <= col <= 2 * devices:
                    raise ValueError("Ambiguous or extra forming measurement column")
                if cell.find(NS + "f") is not None:
                    raise ValueError("Formula or fitted state in forming measurement cells")
                kind, value = cell.get("t", "n"), cell.findtext(NS + "v")
                if kind == "s":
                    index = int(value)
                    if not 0 <= index < len(strings):
                        raise ValueError("Invalid forming shared string")
                    value = strings[index]
                elif kind == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(NS + "t"))
                elif kind not in {"n", "str"}:
                    raise ValueError("Unsupported forming measurement cell type")
                if value in {None, "", "--"}:
                    markers += value == "--"
                    values[col] = None
                else:
                    values[col] = float(value)
                    if not math.isfinite(values[col]):
                        raise ValueError("Nonfinite forming measurement")
            for j in range(devices):
                pair = (values.get(2 * j + 1), values.get(2 * j + 2))
                if None in pair:
                    missing[j].append(number)
                else:
                    traces[j].append(pair)
                    source_rows[j].append(number)
        if not previous or any(len(t) < 100 for t in traces):
            raise ValueError("Insufficient stored forming branch")
        arrays = [np.asarray(t, dtype="<f8") for t in traces]
        for array in arrays:
            prefix = array[:100, 0]
            if np.any(np.diff(prefix) <= 0) or np.any(prefix < 0) or np.any(prefix > 1.02):
                raise ValueError("Initial forming branch is not increasing positive voltage")
        return (
            arrays,
            source_rows,
            {
                "sheet": "Sheet1",
                "source_rows": previous,
                "stored_pairs": sum(map(len, traces)),
                "missing_pair_row_ranges_inclusive": [row_ranges(rows) for rows in missing],
                "explicit_missing_markers": markers,
                "unit_headers": "absent; inherited V/A convention requires source review",
            },
        )


def original_assignments(case, groups):
    from .native import identity

    held = set()
    for prefix in ["I-", "Br-"]:
        members = [g for g in groups if g.startswith(prefix)]
        if len(members) < 12:
            raise ValueError("Insufficient complete traces per composition")
        held.update(
            sorted(
                members, key=lambda g: hashlib.sha256(("ASD6-device-v1|" + g).encode()).hexdigest()
            )[:10]
        )
    ordered = sorted(
        groups - held, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)])
    )
    dev = set(ordered[: max(2, len(ordered) // 5)])
    return {g: "test" if g in held else "dev" if g in dev else "train" for g in groups}


def reconstruct_memristor(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "memristor_archive"]
    (metadata,) = [a for a in recipe["assets"] if a["role"] == "zenodo_record"]
    meta = json.loads(
        contained(source_root, metadata["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if (
        str(meta["id"]) != "17278410"
        or meta["doi"] != "10.5281/zenodo.17278410"
        or meta["metadata"]["version"] != "v1"
        or recipe["input_units"] != {"voltage_V": "V", "bromine_rich": "indicator"}
        or recipe["output_units"] != "microampere"
    ):
        raise ValueError("Memristor source identity, version or unit convention differs")
    inventory, workbooks, duplicates, seen, traces = [], [], {}, {}, {}
    with bounded_zip(
        contained(source_root, asset["path"]), max_bytes=20_000_000, max_member_bytes=3_000_000
    ) as z:
        for comp, (prefix, member) in enumerate(MEMBERS):
            raw = z.read(member)
            arrays, row_ids, info = stored_traces(raw)
            info.update({"member": member, "sha256": hashlib.sha256(raw).hexdigest()})
            workbooks.append(info)
            for j, (array, rows) in enumerate(zip(arrays, row_ids, strict=True)):
                group = f"{prefix}-device-{j + 1:02d}"
                if len(array) != recipe["stored_pairs_per_trace"]:
                    raise ValueError("Registered native trace length changed")
                digest = hashlib.sha256(array.tobytes()).hexdigest()
                if digest in seen:
                    duplicates[group] = seen[digest]
                else:
                    seen[digest] = group
                traces[group] = (array, rows, comp, member, j)
                inventory.append(
                    {
                        "group": group,
                        "member": member,
                        "columns_1based": [2 * j + 1, 2 * j + 2],
                        "source_rows": rows,
                        "complete_trace_sha256": digest,
                        "stored_pairs": len(array),
                    }
                )
    if duplicates != recipe["duplicate_aliases"]:
        raise ValueError("Frozen duplicate aliases changed; source review required")
    groups = set(traces) - set(duplicates)
    assignments = _registered_groups(recipe, groups)
    if assignments != original_assignments(recipe["scenario_id"], groups):
        raise ValueError("Frozen whole-device allocation changed")
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    selected_negative, plateau, total_selected = 0, 0, 0
    for group, (array, rows, comp, member, j) in traces.items():
        if group in duplicates:
            continue
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        for k in range(100):
            voltage, current = array[k]
            if voltage < 0.05:
                continue
            row, origin = _row(
                recipe["scenario_id"],
                f"{recipe['scenario_id']}:{member}:row{rows[k]}:columns{2 * j + 1}-{2 * j + 2}",
                group,
                split,
                {"voltage_V": float(voltage), "bromine_rich": float(comp)},
                float(current * 1e6),
                {"trace": group, "source_row": rows[k], "pair_index0": k},
            )
            parts[split].append(row)
            lineage.append(origin)
            selected_negative += current < 0
            plateau += current == 0.00115
            total_selected += 1
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "memristor_validation": {
                "source_trace_columns": len(traces),
                "distinct_stored_traces": len(groups),
                "stored_pairs_including_duplicate": sum(len(t[0]) for t in traces.values()),
                "duplicate_aliases": duplicates,
                "eligible_rows": total_selected,
                "negative_selected_currents": int(selected_negative),
                "exact_1_15_mA_selected_currents": int(plateau),
                "group_counts": {p: sum(v == p for v in assignments.values()) for p in parts},
                "first_100_pairs_increasing_positive_voltage": True,
                "fitting_performed": False,
            },
            "workbooks": workbooks,
            "trace_inventory": inventory,
            "lineage_definition": "Trace inventory binds member, one-based paired columns and all complete source rows; row lineage identifies one of the first 100 complete pairs. Targets convert stored A to microampere. No current is a predictor.",
            "duplicate_scope": "Fixed retrospective whole-trace alias map, including later responses, is validated, never relearned for evaluation; a changed alias fails instead of changing the cohort. Equality is not proof of shared physical identity.",
            "units_scope": "Workbooks have no unit/header rows; V and A convention follows the frozen native specification and must be reconciled with acquisition metadata before admission",
            "source_instrument_conflict": "Local README names Autolab PGSTAT204; published paper names Keysight B1500A. Acquisition provenance remains unresolved.",
            "response_scope": "Initial increasing positive forming-sweep current at stored voltage >=0.05 V; no later sweep, fitted model, threshold estimate, current calibration or derived resistance in predictors",
            "independence_scope": "Complete source-column traces separated; physical device identifiers and manufacturing batch allocation are absent. Accuracy alone does not identify mechanisms or establish out-of-batch transfer.",
            "recommended_edition_role": "pending_source_provenance_and_scientific_review",
            "admission_blockers": [
                "Resolve instrument/unit provenance and physical device/batch identities",
                "Reconcile 1.15 mA stored plateaus with reported 1 mA compliance before mechanistic interpretation",
                "Verify duplicate-trace origin; no new independent cell is inferred from its column label",
                "Complete rights/notices and scenario-specific perturbation standards",
            ],
        },
    )
