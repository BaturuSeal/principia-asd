import io
import json
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
import pytest

from principia_asd.catalog.fracture import NS, REL
from principia_asd.catalog.native import reconstruct
from principia_asd.catalog.xas import (
    ASSIGNMENT,
    CLOCK,
    INPUT_UNITS,
    RAW,
    REFERENCES,
    SEGMENTS,
    acquisition_clock,
    calibrated_panel,
    original_assignments,
    reconstruct_xas,
    stored_assignment,
    stored_spectra,
)
from principia_asd.io import file_sha


def array_bytes(a, header):
    s = io.StringIO()
    np.savetxt(s, a, fmt="%.12g", header=header)
    return s.getvalue().encode()


def spectra():
    e = 6404.221 + np.arange(2005)
    base = 1 + 0.4 * np.tanh((e - 7110) / 10)
    a = np.column_stack([e, *[base + j / 100 for j in range(194)]])
    a[645, 1:] = np.nan  # Same missing 7049.221 eV calibration row as the source.
    re = 6400.041 + np.arange(1873)
    refs = np.column_stack(
        [re, 1 + 0.4 * np.tanh((re - 7110) / 12), 1 + 0.5 * np.tanh((re - 7112) / 10)]
    )
    return a, refs


def assignment_cells():
    v = {
        "B1": "seconds total",
        "C1": "senconds segment",
        "E1": "1xBinning spectra",
        "F1": "3x-Binning spectra",
    }
    for row, values in enumerate(SEGMENTS, 3):
        v.update({f"{c}{row}": x for c, x in zip("ABCEF", values, strict=True)})
    return v


def assignment(values=None, *, formula=False, target="worksheets/sheet1.xml"):
    book = ET.Element(NS + "workbook")
    sheets = ET.SubElement(book, NS + "sheets")
    ET.SubElement(sheets, NS + "sheet", {"name": "Tabelle1", REL + "id": "r1"})
    links = ET.Element("Relationships")
    ET.SubElement(links, "Relationship", {"Id": "r1", "Target": target})
    root = ET.Element(NS + "worksheet")
    data = ET.SubElement(root, NS + "sheetData")
    values = assignment_cells() if values is None else values
    for n in range(1, 7):
        row = ET.SubElement(data, NS + "row", {"r": str(n)})
        for address, value in values.items():
            if int(address[1:]) != n:
                continue
            c = ET.SubElement(row, NS + "c", {"r": address})
            if isinstance(value, str):
                c.set("t", "inlineStr")
                ET.SubElement(ET.SubElement(c, NS + "is"), NS + "t").text = value
            else:
                ET.SubElement(c, NS + "v").text = str(value)
            if formula and address == "B3":
                ET.SubElement(c, NS + "f").text = "HIDDEN_FIT()"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, node in {
            "xl/workbook.xml": book,
            "xl/_rels/workbook.xml.rels": links,
            "xl/worksheets/sheet1.xml": root,
        }.items():
            z.writestr(name, ET.tostring(node))
    return out.getvalue()


def clock():
    lines = [""] * 21
    lines[0] = "date [dd.mm.yy]\t07.06.23"
    lines[1] = "measurement_ID LFP"
    lines[19] = "number total time segment time period voltage current capacity criterion mode"
    lines[20] = "[1] [s] [s] [s] [V] [A] [mAh/g] [V or A] [1]"
    a = np.zeros((58068, 9))
    a[:, 0] = np.arange(len(a))
    a[:, 1] = np.arange(len(a))
    a[:, 3] = 0.5
    for i, (lo, hi) in enumerate(
        zip([0, 31982, 39182, 50867], [31982, 39182, 50867, 58068], strict=True)
    ):
        a[lo:hi, 2] = np.arange(hi - lo) + (0.5 if i == 1 else 0)
        a[lo:hi, -1] = (1, 0, 3, 0)[i]
    out = io.StringIO()
    out.write("\n".join(lines) + "\n")
    np.savetxt(out, a, fmt="%.6f")
    return out.getvalue().encode()


@pytest.fixture(scope="module")
def sources():
    a, refs = spectra()
    return {
        RAW: array_bytes(a, "energy_eV " + " ".join(f"{i:03}" for i in range(1, 195))),
        REFERENCES: array_bytes(refs, "energy_eV FePO4 LiFePO4"),
        ASSIGNMENT: assignment(),
        CLOCK: clock(),
    }


def save(tmp_path, sources):
    path = tmp_path / "data.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, raw in sources.items():
            z.writestr(name, raw)
    return path


def recipe(tmp_path, sources):
    p = save(tmp_path, sources)
    meta = tmp_path / "metadata.json"
    meta.write_text(
        json.dumps(
            {
                "id": 14922524,
                "doi": "10.5281/zenodo.14922524",
                "metadata": {"license": {"id": "cc-by-4.0"}},
            }
        )
    )
    return {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-025",
        "parser": "lfp-native-calibrated-xanes-v1",
        "input_units": INPUT_UNITS.copy(),
        "output_units": "dimensionless μ(E)",
        "group_assignments": original_assignments("P100-025"),
        "assets": [
            {"path": f.name, "role": role, "bytes": f.stat().st_size, "sha256": file_sha(f)}
            for f, role in [(p, "xas_archive"), (meta, "source_metadata")]
        ],
    }


def test_complete_triplets_calibration_and_target_custody(tmp_path, sources):
    parts, lineage, checks = reconstruct(recipe(tmp_path, sources), tmp_path)
    assert {s: len(v) for s, v in parts.items()} == {"train": 3276, "dev": 754, "test": 1014}
    assert checks["split_check"]["valid"] and len(lineage) == 5044
    assert all("target" not in r for r in parts["test"])
    v = checks["xas_validation"]
    assert v["group_counts"] == {"train": 42, "dev": 10, "test": 13}
    assert v["missing_native_measurements"] == 194 and v["fit_count"] == 0
    assert len(checks["xas_spectra"]) == 194 and checks["xas_spectra"][0]["pre_count"] == 49
    assert v["acquisition_clock"]["rows"] == 58068
    assert len(v["reference_lineage"]) == 26
    assert v["finite_native_measurements"] == 388970 - 194
    assert v["acquisition_clock"]["segments"][2]["start_s"] == 39182
    assert v["protocol"][2]["duration_s"] == 11684
    assert set(parts["train"][0]) == {"sample_id", "group", "target", *INPUT_UNITS}


@pytest.mark.parametrize("split", ["train", "test"])
def test_unseen_spectral_targets_never_change_inputs(tmp_path, sources, split):
    r = recipe(tmp_path, sources)
    before, _, _ = reconstruct_xas(r, tmp_path)
    a = stored_spectra(sources[RAW])
    g = next(g for g, s in r["group_assignments"].items() if s == split)
    col = 3 * int(g[-2:]) + 1
    a[(a[:, 0] >= 7070) & (a[:, 0] <= 7200), col] += 5
    changed = dict(sources)
    changed[RAW] = array_bytes(a, "energy_eV " + " ".join(f"{i:03}" for i in range(1, 195)))
    save(tmp_path, changed)
    after, _, _ = reconstruct_xas(r, tmp_path)

    def inputs(parts):
        return {
            s: [{k: v for k, v in row.items() if k != "target"} for row in rows]
            for s, rows in parts.items()
        }

    assert inputs(before) == inputs(after)
    assert (before != after) == (split == "train")


def test_reference_interpolation_gradients_and_calibration_are_expanded():
    a, r = spectra()
    sel, base, jump, features, bands = calibrated_panel(a, r)
    assert len(sel) == 26 and len(bands["raw_pre_rows"]) == 50
    assert np.allclose(jump, 0.8)
    assert np.allclose(base, np.arange(194) / 100 + 0.6)
    assert set(features) == {"rL", "rF", "dL", "d2L"}
    k = np.argmin(abs(a[sel, 0] - 7112))
    assert features["dL"][k] > 0
    assert features["d2L"][0] > 0 and features["d2L"][-1] < 0
    # Changing one permitted calibration only affects that spectrum, never a learned shared fit.
    a[(a[:, 0] >= 7000) & (a[:, 0] <= 7050), 2] += 0.1
    _, new_base, new_jump, new_features, _ = calibrated_panel(a, r)
    assert new_base[1] == pytest.approx(base[1] + 0.1) and new_jump[1] == pytest.approx(
        jump[1] - 0.1
    )
    assert np.array_equal(new_base[np.arange(194) != 1], base[np.arange(194) != 1])
    assert all(np.array_equal(features[k], new_features[k]) for k in features)


@pytest.mark.parametrize(
    "change", ["negative_jump", "empty_band", "missing_target", "reference_jump"]
)
def test_bad_calibration_or_missing_target_cannot_shrink_cohort(change):
    a, r = spectra()
    if change == "negative_jump":
        a[(a[:, 0] >= 7250) & (a[:, 0] <= 7300), 1] = -99
    elif change == "empty_band":
        a[(a[:, 0] >= 7000) & (a[:, 0] <= 7050), 1] = np.nan
    elif change == "missing_target":
        a[666, 1] = np.nan
    else:
        r[:, 1] = 1
    with pytest.raises(ValueError):
        calibrated_panel(a, r)


@pytest.mark.parametrize(
    "change", ["header", "column", "energy_order", "energy_unit", "inf", "missing_ref"]
)
def test_native_spectrum_guards(sources, change):
    reference = change == "missing_ref"
    raw = sources[REFERENCES if reference else RAW]
    if change == "header":
        raw = raw.replace(b"001", b"002", 1)
    elif change == "column":
        raw = raw.replace(b" 194\n", b" extra\n", 1)
    else:
        a = stored_spectra(raw, reference=reference)
        if change == "energy_order":
            a[1, 0] = a[0, 0]
        elif change == "energy_unit":
            a[:, 0] /= 1000
        elif change == "inf":
            a[1, 1] = np.inf
        else:
            a[1, 1] = np.nan
        raw = array_bytes(
            a,
            "energy_eV FePO4 LiFePO4"
            if reference
            else "energy_eV " + " ".join(f"{i:03}" for i in range(1, 195)),
        )
    with pytest.raises(ValueError):
        stored_spectra(raw, reference=reference)


@pytest.mark.parametrize("change", ["duration", "spectra", "units", "formula", "traversal"])
def test_source_assignment_guards(change):
    values = assignment_cells()
    if change == "duration":
        values["C5"] = 11685
    elif change == "spectra":
        values["E5"] = "131-170"
    elif change == "units":
        values["B1"] = "minutes total"
    with pytest.raises(ValueError):
        stored_assignment(
            assignment(
                values,
                formula=change == "formula",
                target="../secret.xml" if change == "traversal" else "worksheets/sheet1.xml",
            )
        )


@pytest.mark.parametrize("change", ["unit", "time", "mode", "segment"])
def test_electrochemistry_clock_guards(sources, change):
    raw = sources[CLOCK]
    if change == "unit":
        raw = raw.replace(b"[s]", b"[ms]", 1)
    else:
        ls = raw.decode().splitlines()
        v = ls[22].split()
        v[{"time": 1, "mode": 8, "segment": 2}[change]] = "-1"
        ls[22] = " ".join(v)
        raw = "\n".join(ls).encode()
    with pytest.raises(ValueError):
        acquisition_clock(raw)


def test_unused_binning_fit_and_voltage_channels_do_not_change_predictors(tmp_path, sources):
    r = recipe(tmp_path, sources)
    before, _, _ = reconstruct_xas(r, tmp_path)
    changed = dict(sources)
    changed["01_XANES/LFP/LFP_3xBin_01-65.dat"] = b"not an additional independent sample"
    changed["05_CIF/author-fitted-state.txt"] = b"ignored"
    ls = changed[CLOCK].decode().splitlines()
    for i in range(21, len(ls)):
        v = ls[i].split()
        v[4] = "-99999"
        v[5] = "123456"
        v[6] = "98765"
        ls[i] = " ".join(v)
    changed[CLOCK] = "\n".join(ls).encode()
    save(tmp_path, changed)
    after, _, _ = reconstruct_xas(r, tmp_path)
    assert before == after


@pytest.mark.parametrize("change", ["unit", "split", "source_hash"])
def test_source_and_whole_triplet_bindings(tmp_path, sources, change):
    r = recipe(tmp_path, sources)
    if change == "unit":
        r["input_units"]["f"] = "measured state of charge"
    elif change == "split":
        r["group_assignments"]["triplet-00"] = "test"
    else:
        r["assets"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        (reconstruct if change == "source_hash" else reconstruct_xas)(r, tmp_path)
