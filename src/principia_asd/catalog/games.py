"""Stored first-session contributions and causal, within-pair history only.

The Type2 sheets mirror the same games. They verify identity and measurement
consistency; they never add samples. Surveys and second sessions are excluded.
"""

import re
from pathlib import PurePosixPath

import numpy as np

from ..io import contained
from .curves import _number
from .fracture import NS, REL, bounded_zip
from .splits import check_units

PARAMETERS = {
    "Full_equality": (24, 24, 1, 1),
    "Endowment_inequality": (36, 12, 1, 1),
    "Productivity_inequality": (24, 24, 3, 1),
    "Aligned_inequality": (36, 12, 3, 1),
    "Misaligned_inequality": (36, 12, 1, 3),
}
COLUMNS = "CDEFGHIJKLMNOPQRSTUV"


def stored_games(path):
    """Decode measured cells without executing formulas or loading source code."""
    from .native import _xml

    result = {}
    with bounded_zip(path, max_bytes=3_000_000, max_member_bytes=500_000) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = [
                "".join(t.text or "" for t in item.iter(NS + "t"))
                for item in _xml(z.read("xl/sharedStrings.xml")).findall(NS + "si")
            ]
        sheets = _xml(z.read("xl/workbook.xml")).findall(f"{NS}sheets/{NS}sheet")
        expected = {f"{name}_Type{role}" for name in PARAMETERS for role in (1, 2)}
        if len(sheets) != len(expected) or {s.get("name") for s in sheets} != expected:
            raise ValueError("Unexpected threshold-game worksheet inventory")
        links = _xml(z.read("xl/_rels/workbook.xml.rels"))
        members = set()
        for sheet in sheets:
            name = sheet.get("name")
            matches = [r for r in links if r.get("Id") == sheet.get(REL + "id")]
            if len(matches) != 1 or matches[0].get("TargetMode") == "External":
                raise ValueError("Unresolved or external game worksheet")
            target = PurePosixPath(matches[0].get("Target", ""))
            if target.is_absolute() or ".." in target.parts:
                raise ValueError("Unsafe game worksheet relationship")
            member = "xl/" + str(target)
            if member in members:
                raise ValueError("Repeated game worksheet member")
            members.add(member)
            rows, previous = {}, 0
            for row in _xml(z.read(member)).findall(f"{NS}sheetData/{NS}row"):
                number = int(row.attrib["r"])
                if number != previous + 1:
                    raise ValueError("Missing, duplicate or reordered game source row")
                previous = number
                if number > 1 and (number - 2) % 4 >= 2:
                    continue  # Session 2 never enters the selected task.
                cells = {}
                for cell in row.findall(NS + "c"):
                    match = re.fullmatch(r"([A-V])([1-9][0-9]*)", cell.get("r", ""))
                    if not match:
                        continue  # Post-session survey responses W:Z are excluded.
                    column, cell_row = match.groups()
                    if int(cell_row) != number or column in cells:
                        raise ValueError("Ambiguous game measurement cell")
                    if cell.find(NS + "f") is not None:
                        raise ValueError("Formula in selected game measurement or identity")
                    kind, value = cell.get("t", "n"), cell.findtext(NS + "v")
                    if kind == "s":
                        index = int(value)
                        if not 0 <= index < len(strings):
                            raise ValueError("Invalid game source string index")
                        value = strings[index]
                    elif kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(NS + "t"))
                    elif kind not in {"n", "str"}:
                        raise ValueError("Unsupported game measurement cell type")
                    cells[column] = value
                rows[number] = cells
            headers = {"A": "NO.", "B": "Participant"}
            headers.update({column: f"R_{i}" for i, column in enumerate(COLUMNS, 1)})
            if rows.pop(1, None) != headers or previous <= 1 or (previous - 1) % 4:
                raise ValueError("Invalid round headers or incomplete participant block")
            result[name] = {"rows": rows, "pairs": (previous - 1) // 4, "member": member}
    return result


def _participant(value):
    if not re.fullmatch(r"[1-9][0-9]*", value or ""):
        raise ValueError("Unresolved game participant identity")
    return int(value)


def _peer(value, role):
    match = re.fullmatch(rf"Type{role}_0*([1-9][0-9]*)", value or "")
    if not match:
        raise ValueError("Unresolved first-session peer identity")
    return int(match[1])


def _contributions(rows, first, endowments):
    values = np.asarray([[_number(rows[first + role].get(c)) for c in COLUMNS] for role in (0, 1)])
    if any(
        np.any(values[role] < 0)
        or np.any(values[role] > endowments[role])
        or np.any(values[role] != np.floor(values[role]))
        for role in (0, 1)
    ):
        raise ValueError("Contribution outside declared integer-token action space")
    return values


def reconstruct_games(recipe, source_root):
    from .native import _registered_groups, _row, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "threshold_game_workbook"]
    sheets = stored_games(contained(source_root, asset["path"]))
    expected_parameters = {k: list(v) for k, v in PARAMETERS.items()}
    if recipe["treatment_parameters"] != expected_parameters:
        raise ValueError("Unregistered game parameter or treatment change")
    groups = {
        f"{treatment}-pair{i}"
        for treatment in PARAMETERS
        for i in range(1, sheets[treatment + "_Type1"]["pairs"] + 1)
    }
    assignments = _registered_groups(recipe, groups)
    parts, lineage, units, pairs = {p: [] for p in ("train", "dev", "test")}, [], {}, []
    for treatment, (e1, e2, p1, p2) in PARAMETERS.items():
        sheet, mirror = (sheets[treatment + f"_Type{role}"] for role in (1, 2))
        count = sheet["pairs"]
        if mirror["pairs"] != count or count != recipe["source_pair_counts"][treatment]:
            raise ValueError("Unregistered participant count or unmatched mirror sheet")
        rows, mirrored, peer_ids = sheet["rows"], mirror["rows"], set()
        for i in range(1, count + 1):
            first = 4 * i - 2
            if _participant(rows[first].get("A")) != i or rows[first].get("B") != "me":
                raise ValueError("Canonical participant identity or role mismatch")
            peer = _peer(rows[first + 1].get("B"), 2)
            if not 1 <= peer <= count or peer in peer_ids:
                raise ValueError("Duplicate or unavailable first-session participant")
            peer_ids.add(peer)
            mirror_first = 4 * peer - 2
            if (
                _participant(mirrored[mirror_first].get("A")) != peer
                or _peer(mirrored[mirror_first].get("B"), 1) != i
                or mirrored[mirror_first + 1].get("B") != "me"
                or rows[first + 1].get("A") not in {None, ""}
                or mirrored[mirror_first + 1].get("A") not in {None, ""}
            ):
                raise ValueError("Nonreciprocal participant pairing or ambiguous identity")
            values = _contributions(rows, first, (e1, e2))
            if not np.array_equal(values, _contributions(mirrored, mirror_first, (e1, e2))):
                raise ValueError("Mirrored first-session contributions disagree")
            group = f"{treatment}-pair{i}"
            split = assignments[group]
            units[identity(recipe["scenario_id"], "group", group)] = group
            threshold = (p1 * e1 + p2 * e2) / 2
            pairs.append(
                {
                    "group": group,
                    "split": split,
                    "participants": [f"{treatment}:Type1:{i}", f"{treatment}:Type2:{peer}"],
                    "canonical_sheet": treatment + "_Type1",
                    "canonical_rows": [first, first + 1],
                    "mirror_sheet": treatment + "_Type2",
                    "mirror_rows": [mirror_first, mirror_first + 1],
                    "mirror_values_equal": True,
                }
            )
            for role in (0, 1):
                endowment, peer_endowment = (e1, e2) if role == 0 else (e2, e1)
                prod, peer_prod = (p1, p2) if role == 0 else (p2, p1)
                for t in range(2, 20):
                    previous, peer_previous = values[role, t - 1], values[1 - role, t - 1]
                    row, source = _row(
                        recipe["scenario_id"],
                        f"{group}-player{role + 1}-round{t + 1}",
                        group,
                        split,
                        {
                            "round": t + 1,
                            "own_previous": float(previous),
                            "peer_previous": float(peer_previous),
                            "own_lag2": float(values[role, t - 2]),
                            "peer_lag2": float(values[1 - role, t - 2]),
                            "own_history_mean": float(values[role, :t].mean()),
                            "peer_history_mean": float(values[1 - role, :t].mean()),
                            "endowment": endowment,
                            "peer_endowment": peer_endowment,
                            "productivity": prod,
                            "peer_productivity": peer_prod,
                            "threshold": threshold,
                            "previous_success": float(
                                p1 * values[0, t - 1] + p2 * values[1, t - 1] >= threshold - 1e-9
                            ),
                            "required_contribution": float(
                                np.clip(
                                    (threshold - peer_prod * peer_previous) / prod, 0, endowment
                                )
                            ),
                        },
                        values[role, t],
                        {
                            "source": asset["path"],
                            "sheet": treatment + "_Type1",
                            "own_row": first + role,
                            "peer_row": first + 1 - role,
                            "target_column": COLUMNS[t],
                            "history_columns_inclusive": ["C", COLUMNS[t - 1]],
                            "lag2_column": COLUMNS[t - 2],
                            "round": t + 1,
                        },
                    )
                    parts[split].append(row)
                    lineage.append(source)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "first_session_pairs": pairs,
            "game_validation": {
                "pairs": len(pairs),
                "source_participants": len({v for pair in pairs for v in pair["participants"]}),
                "canonical_measurements": len(pairs) * 40,
                "mirrored_measurements_checked_not_added": len(pairs) * 40,
                "first_two_rounds_are_history_only": True,
                "same_or_future_rounds_used_as_inputs": False,
                "session2_and_surveys_used_as_inputs": False,
                "history_scope": "One-step online conditioning on strictly earlier observed contributions, including earlier held-out responses; not free-running simulation",
                "independence_scope": "First-session interacting pairs kept whole; treatment-qualified source participant IDs are unique; broader recruitment/site dependence unassessed",
            },
        },
    )
