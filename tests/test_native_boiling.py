import json
import xml.etree.ElementTree as ET

import pytest

from principia_asd.catalog.boiling import (
    HELD,
    INPUT_UNITS,
    PC,
    RADIAL_ARRAYS,
    TOP_SCALARS,
    original_assignments,
    reconstruct_boiling,
    saturation,
    saturation_pressure,
    stored_run,
)
from principia_asd.catalog.native import identity, reconstruct
from principia_asd.io import file_sha

GROUPS = [
    "ID_20230630_Run_31",
    "ID_20230630_Run_32",
    "ID_20230808_Run_02",
    "ID_20230808_Run_07",
    "ID_20230809_Run_09",
    "ID_20230809_Run_10",
    "ID_20230809_Run_13",
    "ID_20230809_Run_16",
    "ID_20230809_Run_18",
    "ID_20230809_Run_20",
    "ID_20230810_Run_04",
    "ID_20230810_Run_07",
]


def source(group):
    root = ET.Element(group)
    for key in sorted(TOP_SCALARS):
        ET.SubElement(root, key).text = "0"
    for key, value in {
        "ID": group.split("_")[1],
        "RUN": int(group.split("_")[-1]),
        "PRESSURE": 7_000_000,
        "MASSFLUX": 500,
        "XOUT": 0.1,
        "DISPERSEDPHASE": "vapor" if group in {GROUPS[1], GROUPS[2], GROUPS[9]} else "liquid",
    }.items():
        root.find(key).text = str(value)
    ET.SubElement(root, "pressuredrop")
    ET.SubElement(root, "walltemperature")
    for j in range(12):
        radial = ET.SubElement(root, "radial")
        ET.SubElement(radial, "RADIUS").text = str(8 - j / 2)
        ET.SubElement(radial, "VOIDFRACTION").text = str(0.2 + j / 20)
    return root


def save(path, root):
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def fixture(tmp_path):
    roots, assets = {}, []
    for group in GROUPS:
        root = source(group)
        path = tmp_path / (group + ".xml")
        save(path, root)
        roots[group] = root
        assets.append((path, "boiling_run"))
    metadata = tmp_path / "record.json"
    metadata.write_text(json.dumps({"id": 14627088, "doi": "10.5281/zenodo.14627088"}))
    readme = tmp_path / "readme.txt"
    readme.write_text("SI units have been used; inlet and wall temperatures in Celsius")
    assets += [(metadata, "zenodo_record"), (readme, "source_readme")]
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-027",
        "parser": "kth-boiling-pressure-properties-v1",
        "input_units": INPUT_UNITS.copy(),
        "output_units": "dimensionless",
        "group_assignments": original_assignments("P100-027", set(GROUPS)),
        "assets": [
            {"path": f.name, "role": role, "bytes": f.stat().st_size, "sha256": file_sha(f)}
            for f, role in assets
        ],
    }
    return recipe, roots


@pytest.mark.parametrize(
    "pressure,temperature,liquid,vapor",
    [
        (611.657, 273.16, 999.789, 0.00485426),
        (101325, 373.1243, 958.365, 0.597586),
        (22064000, 647.096, 322, 322),
    ],
)
def test_published_iapws_computer_verification_table(pressure, temperature, liquid, vapor):
    # Wagner/Pruss 1993 appendix Table 1; tolerances reflect printed precision.
    t, rl, rv = saturation(pressure)
    assert t == pytest.approx(temperature, abs=5e-4)
    assert rl == pytest.approx(liquid, abs=0.001)
    assert rv == pytest.approx(vapor, rel=3e-6)


@pytest.mark.parametrize("pressure", [0, 611, PC + 1, float("inf"), float("nan")])
def test_out_of_domain_pressure_cannot_be_extrapolated(pressure):
    with pytest.raises(ValueError):
        saturation(pressure)


@pytest.mark.parametrize("temperature", [273, 648, float("nan")])
def test_out_of_domain_temperature_rejected(temperature):
    with pytest.raises(ValueError):
        saturation_pressure(temperature)


def test_complete_cohort_date_dependence_and_exact_xml_coordinates(tmp_path):
    recipe, _ = fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert {p: len(r) for p, r in parts.items()} == {"train": 84, "dev": 24, "test": 36}
    assert checks["split_check"]["valid"]
    v = checks["boiling_validation"]
    assert v["source_dates"] == 4 and v["runs"] == 12 and v["radial_measurements"] == 144
    assert v["fit_count"] == v["target_calibration_count"] == 0 and v["bisection_iterations"] == 960
    assert v["shared_source_dates"] == {
        "2023-08-08": ["dev", "train"],
        "2023-08-09": ["test", "train"],
        "2023-08-10": ["dev", "train"],
    }
    by_id = {r["sample_id"]: r for rows in parts.values() for r in rows}
    for origin in lineage:
        group = origin["source"][:-4]
        j = origin["source_radial_index_1based"]
        r = by_id[origin["sample_id"]]
        assert r["sample_id"] == identity("P100-027", "sample", f"{group}:radial{j:02d}")
        assert r["group"] == identity("P100-027", "group", group)
        assert r["radial_fraction"] == (8 - (j - 1) / 2) / 8
        assert r["rho_liquid"] > r["rho_vapor"] > 0
        assert set(r) == {
            "sample_id",
            "group",
            *INPUT_UNITS,
            *([] if origin["split"] == "test" else ["target"]),
        }
    assert not any("target" in r for r in parts["test"])


def test_test_responses_and_excluded_channels_do_not_enter_inputs(tmp_path):
    recipe, roots = fixture(tmp_path)
    before = reconstruct(recipe, tmp_path)[0]
    for group, root in roots.items():
        for key in ["POWER", "HEATFLUX", "HOUT", "TIN", "XIN"]:
            root.find(key).text = "untrusted omitted channel"
        for radial in root.findall("radial"):
            ET.SubElement(radial, "DYNPRESSURE").text = "arbitrary omitted response"
            ET.SubElement(radial, "VELOCITY").text = "author fitted value"
            if group in HELD:
                radial.find("VOIDFRACTION").text = "0.99"
        save(tmp_path / (group + ".xml"), root)
    assert reconstruct_boiling(recipe, tmp_path)[0] == before
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, tmp_path)


def test_coordinate_unit_rescaling_does_not_invent_physical_radius():
    root = source(GROUPS[0])
    a, features, info = stored_run(ET.tostring(root), GROUPS[0])
    for radial in root.findall("radial"):
        radial.find("RADIUS").text = str(float(radial.findtext("RADIUS")) * 1000)
    b, features2, info2 = stored_run(ET.tostring(root), GROUPS[0])
    assert features == features2
    assert [r / info["native_coordinate_maximum"] for r, y in a] == [
        r / info2["native_coordinate_maximum"] for r, y in b
    ]
    assert "unresolved" in info["native_coordinate_unit"]


def test_full_distribution_channels_are_counted_but_not_features():
    root = source(GROUPS[2])
    for radial in root.findall("radial"):
        for name in sorted(RADIAL_ARRAYS):
            for _ in range(200):
                ET.SubElement(radial, name).text = "0.1"
    _, features, info = stored_run(ET.tostring(root), GROUPS[2])
    assert all(info["radial_channel_cells"][k] == 2400 for k in RADIAL_ARRAYS)
    assert not RADIAL_ARRAYS & features.keys()
    root.find("radial").remove(root.find("radial/NUMBERDENSITY"))
    with pytest.raises(ValueError, match="inventory"):
        stored_run(ET.tostring(root), GROUPS[2])


@pytest.mark.parametrize(
    "mutation",
    [
        "identity",
        "header",
        "run",
        "duplicate_pressure",
        "missing_quality",
        "nested_scalar",
        "attribute",
        "nonfinite",
        "negative_flux",
        "quality",
        "response",
        "radius_zero",
        "radius_duplicate",
        "radius_order",
        "radial_count",
        "hidden_state",
        "bad_date",
    ],
)
def test_source_identity_domain_and_structure_guards(mutation):
    group = GROUPS[0]
    root = source(group)
    if mutation == "identity":
        root.tag = GROUPS[1]
    if mutation == "header":
        root.find("ID").text = "20230808"
    if mutation == "run":
        root.find("RUN").text = "32"
    if mutation == "duplicate_pressure":
        ET.SubElement(root, "PRESSURE").text = "7e6"
    if mutation == "missing_quality":
        root.remove(root.find("XOUT"))
    if mutation == "nested_scalar":
        ET.SubElement(root.find("PRESSURE"), "fitted").text = "7e6"
    if mutation == "attribute":
        root.find("PRESSURE").set("unit", "MPa")
    if mutation == "nonfinite":
        root.find("PRESSURE").text = "nan"
    if mutation == "negative_flux":
        root.find("MASSFLUX").text = "-1"
    if mutation == "quality":
        root.find("XOUT").text = "1.01"
    if mutation == "response":
        root.find("radial/VOIDFRACTION").text = "1.01"
    if mutation == "radius_zero":
        root.find("radial/RADIUS").text = "0"
    if mutation == "radius_duplicate":
        root.findall("radial")[1].find("RADIUS").text = "8"
    if mutation == "radius_order":
        root.findall("radial")[1].find("RADIUS").text = "9"
    if mutation == "radial_count":
        root.remove(root.find("radial"))
    if mutation == "hidden_state":
        ET.SubElement(root, "fitted_state").text = "hidden"
    if mutation == "bad_date":
        group = "ID_20230231_Run_31"
        root.tag = group
    with pytest.raises(ValueError):
        stored_run(ET.tostring(root), group)


@pytest.mark.parametrize("mutation", ["allocation", "phase", "units", "readme", "source_id"])
def test_frozen_recipe_and_source_provenance_guards(tmp_path, mutation):
    recipe, roots = fixture(tmp_path)
    if mutation == "allocation":
        recipe["group_assignments"][GROUPS[0]] = "train"
    if mutation == "phase":
        roots[GROUPS[0]].find("DISPERSEDPHASE").text = "vapor"
        save(tmp_path / (GROUPS[0] + ".xml"), roots[GROUPS[0]])
    if mutation == "units":
        recipe["input_units"]["pressure_Pa"] = "MPa"
    if mutation == "readme":
        (tmp_path / "readme.txt").write_text("Unknown units")
    if mutation == "source_id":
        (tmp_path / "record.json").write_text(
            json.dumps({"id": 1, "doi": "10.5281/zenodo.14627088"})
        )
    with pytest.raises(ValueError):
        reconstruct_boiling(recipe, tmp_path)


def test_xml_external_entities_and_oversized_payloads_are_rejected():
    for raw in [
        b'<!DOCTYPE x [<!ENTITY xx SYSTEM "file:///private-targets">]><x/>',
        b" " * 1_000_001,
    ]:
        with pytest.raises(ValueError):
            stored_run(raw, GROUPS[0])
