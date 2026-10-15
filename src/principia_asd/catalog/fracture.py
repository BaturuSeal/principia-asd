"""Curator-only stored geometry and native PI 89 traces; no event identification.

Full traces are decoded for identity/measurement validation, never supplied as
inputs to the historical geometry-to-failure-load prediction task.
"""

import hashlib
import io
import math
import re
import stat
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

import numpy as np

from ..io import contained
from .splits import check_units

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
SUMMARY = "Data for publication/Result analysis.xlsx"
TRACE_PREFIX = "Data for publication/Experimental data file (txt)/"
HEADERS = ["Depth (nm)", "Load (µN)", "Time (s)", "Depth (V)", "Load (V)"]
FIELDS = {
    "B": "width_um",
    "C": "thickness_um",
    "D": "length_um",
    "E": "notch_depth_um",
    "I": "notch_width_um",
}


@contextmanager
def bounded_zip(source, *, max_bytes, max_member_bytes, max_members=512):
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        names = [a.filename for a in entries]
        if (
            len(entries) > max_members
            or len(names) != len(set(names))
            or sum(a.file_size for a in entries) > max_bytes
            or any(a.file_size > max_member_bytes for a in entries)
        ):
            raise ValueError("Duplicate or oversized native archive")
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in entry.filename
                or str(path) != entry.filename.rstrip("/")
                or stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK
                or entry.flag_bits & 1
            ):
                raise ValueError("Unsafe, linked or encrypted native archive member")
        yield archive


def decode_trace(raw):
    """Return all stored trace channels with source coordinates and explicit units."""
    if len(raw) > 4_000_000:
        raise ValueError("Oversized native fracture trace")
    lines = raw.decode("cp1252", errors="strict").splitlines()
    if len(lines) < 5 or lines[1].strip() or lines[3].split("\t") != HEADERS:
        raise ValueError("Unexpected native trace header or units")
    count = re.fullmatch(r"Number of Points = ([1-9][0-9]*)", lines[2])
    if not count:
        raise ValueError("Invalid native point-count declaration")
    declared = int(count[1])
    measured = [(i, line) for i, line in enumerate(lines[4:], 5) if line.strip()]
    separators = [i for i, line in enumerate(lines[4:], 5) if not line.strip()]
    if len(measured) != declared or any(len(line.split()) != 5 for _, line in measured):
        raise ValueError("Native point count or measurement row shape mismatch")
    array = np.loadtxt(io.StringIO("\n".join(line for _, line in measured)), ndmin=2)
    if (
        array.shape != (declared, 5)
        or not np.all(np.isfinite(array))
        or len(array) < 2
        or not np.all(np.diff(array[:, 2]) > 0)
    ):
        raise ValueError("Invalid native trace values or acquisition clock")
    # Negative loads/displacements and abrupt changes are real measurements, not filtered.
    segments = []
    for index, (line, _) in enumerate(measured):
        if not segments or line != segments[-1]["last_source_line"] + 1:
            segments.append(
                {
                    "first_source_line": line,
                    "last_source_line": line,
                    "first_array_row": index,
                    "last_array_row": index,
                }
            )
        else:
            segments[-1].update(last_source_line=line, last_array_row=index)
    return array, {
        "rows": declared,
        "first_measurement_line": measured[0][0],
        "last_measurement_line": measured[-1][0],
        "headers": HEADERS,
        "blank_separator_lines": separators,
        "line_segments": segments,
        "encoding": "cp1252",
        "acquisition_timestamp_raw": lines[0],
        "clock_strictly_increasing": True,
        "fitting_performed": False,
        "failure_event_identified": False,
    }


def canonical_specimen(label):
    if not re.fullmatch(r"(?:2_)?[CDE][1-9][0-9]*(?:-2)?", label):
        raise ValueError("Unrecognized fracture specimen identity")
    return re.sub(r"-2$", "", re.sub(r"^2_", "", label))


def stored_summary(raw):
    from .native import _xml

    result, seen = [], set()
    expected_headers = {
        "A": "SampleID",
        "B": "B(µm)",
        "C": "W(µm)",
        "D": "L(µm)",
        "E": "a(µm)",
        "G": "Pb2(mN)",
        "I": "b(µm)",
    }
    with bounded_zip(io.BytesIO(raw), max_bytes=2_000_000, max_member_bytes=1_000_000) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = [
                "".join(t.text or "" for t in item.iter(NS + "t"))
                for item in _xml(z.read("xl/sharedStrings.xml")).findall(NS + "si")
            ]
        sheets = _xml(z.read("xl/workbook.xml")).findall(f"{NS}sheets/{NS}sheet")
        links = _xml(z.read("xl/_rels/workbook.xml.rels"))
        if len(sheets) != 2 or {s.get("name") for s in sheets} != {
            "Crack arrest present ",
            "Crack arrest absent ",
        }:
            raise ValueError("Unexpected fracture summary worksheet inventory")
        selected_members = set()
        for sheet in sheets:
            matches = [r for r in links if r.get("Id") == sheet.get(REL + "id")]
            if len(matches) != 1 or matches[0].get("TargetMode") == "External":
                raise ValueError("Unresolved or external fracture worksheet")
            target = PurePosixPath(matches[0].get("Target", ""))
            if target.is_absolute() or ".." in target.parts:
                raise ValueError("Unsafe fracture worksheet relationship")
            member = "xl/" + str(target)
            if member in selected_members:
                raise ValueError("Repeated fracture summary worksheet")
            selected_members.add(member)
            previous = 0
            header_seen = False
            for row in _xml(z.read(member)).findall(f"{NS}sheetData/{NS}row"):
                number = int(row.attrib["r"])
                if number <= previous:
                    raise ValueError("Duplicate or reordered source row")
                previous = number
                cells = {}
                for cell in row.findall(NS + "c"):
                    address = cell.get("r", "")
                    match = re.fullmatch(r"([ABCDEGI])([1-9][0-9]*)", address)
                    if not match:
                        continue
                    column, cell_row = match.groups()
                    if int(cell_row) != number or column in cells:
                        raise ValueError("Ambiguous fracture measurement cell")
                    if cell.find(NS + "f") is not None:
                        raise ValueError("Fitted/formula state in selected fracture measurements")
                    kind, value = cell.get("t", "n"), cell.findtext(NS + "v")
                    if kind == "s":
                        index = int(value)
                        if index < 0 or index >= len(strings):
                            raise ValueError("Invalid source string index")
                        value = strings[index]
                    elif kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(NS + "t"))
                    elif kind not in {"n", "str"}:
                        raise ValueError("Unsupported fracture measurement cell")
                    cells[column] = value
                if number == 1:
                    if {
                        k: re.sub(r"\s+", "", v or "") for k, v in cells.items()
                    } != expected_headers:
                        raise ValueError("Unexpected summary measurement columns or units")
                    header_seen = True
                    continue
                label = cells.get("A")
                if label is None or not str(label).strip():
                    if any(cells.get(k) not in {None, ""} for k in [*FIELDS, "G"]):
                        raise ValueError("Unidentified fracture measurement row")
                    continue
                label = str(label).strip()
                group = canonical_specimen(label)
                if label in seen:
                    raise ValueError("Duplicate fracture observation identity")
                seen.add(label)
                try:
                    values = {field: float(cells[column]) for column, field in FIELDS.items()}
                    response = float(cells["G"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("Missing native geometry or reported failure load") from exc
                if (
                    not all(math.isfinite(v) and v > 0 for v in [*values.values(), response])
                    or values["notch_depth_um"] >= values["thickness_um"]
                    or values["notch_width_um"] >= values["width_um"]
                ):
                    raise ValueError("Invalid fracture geometry or reported measurement")
                result.append(
                    {
                        "sample": label,
                        "group": group,
                        "inputs": values,
                        "response": response,
                        "worksheet_member": member,
                        "row": number,
                    }
                )
            if not header_seen:
                raise ValueError("Missing fracture summary measurement headers")
    if not result:
        raise ValueError("No fracture observations")
    return result


def reconstruct_fracture(recipe, source_root):
    from .native import _registered_groups, _row, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "fracture_archive"]
    path = contained(source_root, asset["path"])
    parts, lineage, units, traces = {p: [] for p in ("train", "dev", "test")}, [], {}, []
    with bounded_zip(path, max_bytes=160_000_000, max_member_bytes=4_000_000) as z:
        summary = stored_summary(z.read(SUMMARY))
        assignments = _registered_groups(recipe, {r["group"] for r in summary})
        selected = [n for n in z.namelist() if n.startswith(TRACE_PREFIX) and n.endswith(".txt")]
        members = {Path(n).stem: n for n in selected}
        if (
            len(members) != len(selected)
            or len(members) != len(summary)
            or members.keys() != {r["sample"] for r in summary}
        ):
            raise ValueError("Summary/trace observation identities differ")
        for record in summary:
            label, group = record["sample"], record["group"]
            member = members[label]
            raw = z.read(member)
            _, diagnostics = decode_trace(raw)
            traces.append(
                {"member": member, "source_sha256": hashlib.sha256(raw).hexdigest(), **diagnostics}
            )
            split = assignments[group]
            units[identity(recipe["scenario_id"], "group", group)] = group
            row, source = _row(
                recipe["scenario_id"],
                label,
                group,
                split,
                record["inputs"],
                record["response"],
                {
                    "source": asset["path"],
                    "summary_member": SUMMARY,
                    "worksheet_member": record["worksheet_member"],
                    "summary_row": record["row"],
                    "input_columns": list(FIELDS),
                    "response_column": "G",
                    "native_trace_member": member,
                    "specimen": group,
                    "observation": label,
                    "input_timing": "Reported SEM geometry may be measured post-test; retrospective conditional task",
                    "response_origin": "Stored author-reported Pb2; no automatic peak or fracture-event substitution",
                },
            )
            parts[split].append(row)
            lineage.append(source)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "native_traces": traces,
            "native_measurement_rows": sum(t["rows"] for t in traces),
            "native_traces_exported_as_model_inputs": False,
            "independence_scope": "Complete canonical specimen, with repeat tests kept together; one source wafer/manufacturing campaign",
            "response_scope": "Author-reported second-bridge failure load; trace event identification remains unvalidated",
        },
    )
