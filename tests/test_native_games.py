import copy
import xml.etree.ElementTree as ET
import zipfile

import pytest

from principia_asd.catalog.games import COLUMNS, PARAMETERS
from principia_asd.catalog.native import NS, REL, VERSION, reconstruct
from principia_asd.io import file_sha


def games(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    path = root / "games.xlsx"
    sheets = {}
    for treatment, (e1, e2, _, _) in PARAMETERS.items():
        headers = {"A": "NO.", "B": "Participant"}
        headers.update({c: f"R_{i}" for i, c in enumerate(COLUMNS, 1)})
        a, b = {1: headers}, {1: headers}
        for i in range(1, 4):
            # Reciprocal sheets have a different pair order.
            peer = i % 3 + 1
            r, m = 4 * i - 2, 4 * peer - 2
            for role, endowment in enumerate((e1, e2)):
                values = {c: (i + k) % (endowment + 1) for k, c in enumerate(COLUMNS)}
                a[r + role] = dict(
                    values,
                    A=str(i) if role == 0 else None,
                    B="me" if role == 0 else f"Type2_{peer:02}",
                )
                b[m + role] = dict(
                    values,
                    A=str(peer) if role == 0 else None,
                    B=f"Type1_{i:02}" if role == 0 else "me",
                )
            for rr in (r + 2, r + 3):
                a[rr] = {"C": {"formula": "FORBIDDEN_SESSION2()", "value": "99"}}
            for rr in (m + 2, m + 3):
                b[rr] = {"C": {"formula": "FORBIDDEN_SESSION2()", "value": "99"}}
            a[r]["W"] = {"formula": "POST_SESSION_SURVEY()", "value": "999"}
        sheets[treatment + "_Type1"] = a
        sheets[treatment + "_Type2"] = b
    recipe = {
        "schema_version": VERSION,
        "scenario_id": "P100-087",
        "parser": "threshold-public-goods-session1-v1",
        "treatment_parameters": {k: list(v) for k, v in PARAMETERS.items()},
        "source_pair_counts": dict.fromkeys(PARAMETERS, 3),
        "group_assignments": {
            f"{t}-pair{i}": p for t in PARAMETERS for i, p in enumerate(("train", "dev", "test"), 1)
        },
        "assets": [{"role": "threshold_game_workbook", "path": path.name}],
    }

    def save(modifier=None):
        book = ET.Element(NS + "workbook")
        names = ET.SubElement(book, NS + "sheets")
        links = ET.Element("Relationships")
        members = {}
        for i, (name, rows) in enumerate(sheets.items(), 1):
            ET.SubElement(names, NS + "sheet", {"name": name, REL + "id": f"r{i}"})
            ET.SubElement(links, "Relationship", {"Id": f"r{i}", "Target": f"worksheets/s{i}.xml"})
            sheet = ET.Element(NS + "worksheet")
            data = ET.SubElement(sheet, NS + "sheetData")
            for number, row in sorted(rows.items()):
                rr = ET.SubElement(data, NS + "row", {"r": str(number)})
                for column, value in row.items():
                    attrs = {"r": f"{column}{number}"}
                    if isinstance(value, str):
                        attrs["t"] = "inlineStr"
                    cell = ET.SubElement(rr, NS + "c", attrs)
                    if isinstance(value, str):
                        ET.SubElement(ET.SubElement(cell, NS + "is"), NS + "t").text = value
                    elif isinstance(value, dict):
                        ET.SubElement(cell, NS + "f").text = value["formula"]
                        ET.SubElement(cell, NS + "v").text = value["value"]
                    elif value is not None:
                        ET.SubElement(cell, NS + "v").text = str(value)
            members[f"xl/worksheets/s{i}.xml"] = ET.tostring(sheet)
        members["xl/workbook.xml"] = ET.tostring(book)
        members["xl/_rels/workbook.xml.rels"] = ET.tostring(links)
        if modifier:
            modifier(members)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, value in members.items():
                z.writestr(name, value)
        recipe["assets"][0].update(sha256=file_sha(path), bytes=path.stat().st_size)

    save()
    return root, recipe, sheets, save


def test_games_preserve_canonical_pairs_and_reciprocal_measurements(tmp_path):
    root, recipe, _, _ = games(tmp_path)
    parts, lineage, checks = reconstruct(recipe, root)
    assert {p: len(rows) for p, rows in parts.items()} == dict.fromkeys(parts, 180)
    assert checks["split_check"]["valid"]
    v = checks["game_validation"]
    assert v["pairs"] == 15 and v["source_participants"] == 30
    assert v["canonical_measurements"] == v["mirrored_measurements_checked_not_added"] == 600
    assert not v["session2_and_surveys_used_as_inputs"]
    assert all(
        len([r for r in rows if r["group"] == group]) == 36
        for rows in parts.values()
        for group in {r["group"] for r in rows}
    )
    assert all("target" not in row for row in parts["test"])
    assert lineage[0]["target_column"] == "E"
    assert lineage[0]["history_columns_inclusive"] == ["C", "D"]
    assert lineage[0]["lag2_column"] == "C"
    assert parts["train"][0]["own_history_mean"] == 1.5
    assert parts["train"][0]["target"] == 3
    assert checks["first_session_pairs"][0]["participants"] == [
        "Full_equality:Type1:1",
        "Full_equality:Type2:2",
    ]


def test_excluded_session2_and_survey_values_never_change_results(tmp_path):
    root, recipe, sheets, save = games(tmp_path)
    before = reconstruct(recipe, root)
    for rows in sheets.values():
        for number, row in rows.items():
            row["W"] = "=TARGET_DERIVED_STATE()"
            if number > 1 and (number - 2) % 4 >= 2:
                row.update({c: "nan" for c in "ABCDEFGHIJKLMNOPQRSTUV"})
    save()
    assert reconstruct(recipe, root) == before


def test_terminal_future_test_response_never_changes_public_inputs(tmp_path):
    root, recipe, sheets, save = games(tmp_path)
    before = reconstruct(recipe, root)[0]
    # Pair 3 is held out, with its mirrored peer 1 in the opposite sheet.
    sheets["Full_equality_Type1"][10]["V"] = 0
    sheets["Full_equality_Type2"][2]["V"] = 0
    save()
    assert reconstruct(recipe, root)[0] == before


def test_online_history_uses_only_strictly_earlier_observed_rounds(tmp_path):
    root, recipe, sheets, save = games(tmp_path)
    before = reconstruct(recipe, root)[0]["test"]
    sheets["Full_equality_Type1"][10]["G"] = 0  # Round 5, never input for round <= 5.
    sheets["Full_equality_Type2"][2]["G"] = 0
    save()
    after = reconstruct(recipe, root)[0]["test"]
    assert [r for r in before if r["round"] <= 5] == [r for r in after if r["round"] <= 5]
    assert before != after  # Subsequent predictions legitimately receive observed history.
    changed = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    assert all(a["round"] > 5 for a, _ in changed)


@pytest.mark.parametrize(
    "column,value,error",
    [
        ("A", "2", "Canonical participant"),
        ("B", "Type1_02", "Canonical participant"),
        ("C", "nan", "Nonfinite"),
        ("C", None, "Non-numeric"),
        ("C", -1, "integer-token"),
        ("C", 25, "integer-token"),
        ("C", 1.5, "integer-token"),
        ("C", {"formula": "FIT()", "value": "1"}, "Formula"),
    ],
)
def test_invalid_selected_measurements_and_identity_are_rejected(tmp_path, column, value, error):
    root, recipe, sheets, save = games(tmp_path)
    sheets["Full_equality_Type1"][2][column] = value
    save()
    with pytest.raises(ValueError, match=error):
        reconstruct(recipe, root)


@pytest.mark.parametrize(
    "change,error",
    [
        ("mirror", "Mirrored"),
        ("reciprocity", "Nonreciprocal"),
        ("peer", "Duplicate or unavailable"),
        ("round", "round headers"),
        ("missing_row", "Missing, duplicate"),
        ("parameters", "parameter"),
        ("counts", "participant count"),
        ("group", "independent-unit"),
    ],
)
def test_ambiguous_games_and_frozen_allocations_fail(tmp_path, change, error):
    root, recipe, sheets, save = games(tmp_path)
    if change == "mirror":
        sheets["Full_equality_Type2"][6]["C"] = 0
    elif change == "reciprocity":
        sheets["Full_equality_Type2"][6]["B"] = "Type1_03"
    elif change == "peer":
        sheets["Full_equality_Type1"][3]["B"] = "Type2_99"
    elif change == "round":
        sheets["Full_equality_Type1"][1] = dict(sheets["Full_equality_Type1"][1], E="R_4")
    elif change == "missing_row":
        del sheets["Full_equality_Type1"][4]
    elif change == "parameters":
        recipe["treatment_parameters"]["Full_equality"][0] = 23
    elif change == "counts":
        recipe["source_pair_counts"]["Full_equality"] = 2
    elif change == "group":
        del recipe["group_assignments"]["Full_equality-pair1"]
    save()
    with pytest.raises(ValueError, match=error):
        reconstruct(recipe, root)


def test_external_sheet_and_formula_caches_are_never_followed(tmp_path):
    root, recipe, _, save = games(tmp_path)

    def external(members):
        name = "xl/_rels/workbook.xml.rels"
        xml = ET.fromstring(members[name])
        xml[0].set("TargetMode", "External")
        xml[0].set("Target", "https://example.invalid/sheet.xml")
        members[name] = ET.tostring(xml)

    original = copy.deepcopy(recipe)
    save(external)
    assert recipe["assets"] != original["assets"]
    with pytest.raises(ValueError, match="external game worksheet"):
        reconstruct(recipe, root)
