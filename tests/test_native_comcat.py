import copy
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pytest

from principia_asd.catalog.comcat import (
    CAT,
    NS,
    check_geojson,
    cluster_events,
    decode_quakeml,
    reconstruct_comcat,
    source_test_groups,
    utc_timestamp,
)
from principia_asd.catalog.native import identity, reconstruct
from principia_asd.io import file_sha, sha

B = "{" + NS["b"] + "}"


def snapshot(count=7):
    tree = ET.Element("{http://quakeml.org/xmlns/quakeml/1.2}quakeml")
    params = ET.SubElement(tree, B + "eventParameters")
    features = []
    for i in range(count):
        eid = f"us7000test{i}"
        sid = f"quakeml:earthquake.usgs.gov/fdsnws/event/1/query?eventid={eid}&format=quakeml"
        oid = "origin:" + eid
        event = ET.SubElement(
            params,
            B + "event",
            {"publicID": sid, CAT + "eventsource": "us", CAT + "eventid": eid[2:]},
        )
        origin = ET.SubElement(event, B + "origin", {"publicID": oid})
        for key, value in {
            "time": "2026-07-01T00:00:00.001Z",
            "latitude": 0,
            "longitude": i * 20,
            "depth": -500 + i * 1000,
        }.items():
            field = ET.SubElement(origin, B + key)
            ET.SubElement(field, B + "value").text = str(value)
            if key == "depth":
                ET.SubElement(field, B + "uncertainty").text = str(200 + i)
        quality = ET.SubElement(origin, B + "quality")
        for key, value in {
            "standardError": 0.4,
            "usedPhaseCount": 20,
            "usedStationCount": 12,
            "azimuthalGap": 120,
            "minimumDistance": 0.2,
        }.items():
            ET.SubElement(quality, B + key).text = str(value)
        ET.SubElement(event, B + "preferredOriginID").text = oid
        ET.SubElement(event, B + "type").text = "earthquake"
        features.append(
            {
                "type": "Feature",
                "id": eid,
                "properties": {
                    "time": 1782864000001,
                    "nst": 12,
                    "rms": 0.4,
                    "gap": 120,
                    "dmin": 0.2,
                    "mag": 3,
                },
                "geometry": {"type": "Point", "coordinates": [i * 20, 0, -0.5 + i]},
            }
        )
    geo = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "count": count,
            "api": "2.7.0",
            "status": 200,
            "generated": 1782865000000,
            "url": "https://example.invalid/frozen-query",
        },
    }
    return tree, geo


def encoded(tree):
    return ET.tostring(tree, encoding="utf-8")


def case(tmp_path):
    tree, geo = snapshot()
    rows = decode_quakeml(encoded(tree))
    mapping, _, _ = cluster_events(rows)
    held = source_test_groups(set(mapping.values()))
    development = set(mapping.values()) - held
    dev = set(
        sorted(
            development,
            key=lambda g: sha(["compact-v2", "P100-017", identity("P100-017", "group", g)]),
        )[:2]
    )
    assignment = {
        g: "test" if g in held else "dev" if g in dev else "train" for g in mapping.values()
    }
    data = {
        "catalog.xml": encoded(tree),
        "catalog.json": json.dumps(geo).encode(),
        "count.txt": b"7",
        "version.txt": b"2.7.0",
    }
    roles = ["quakeml_catalog", "geojson_catalog", "catalog_count", "catalog_service_version"]
    assets = []
    for (name, raw), role in zip(data.items(), roles, strict=True):
        path = tmp_path / name
        path.write_bytes(raw)
        assets.append({"path": name, "sha256": file_sha(path), "bytes": len(raw), "role": role})
    return (
        tree,
        geo,
        {
            "scenario_id": "P100-017",
            "schema_version": "native-reconstruction/1",
            "parser": "comcat-origin-quality-clusters-v1",
            "source_query_url": geo["metadata"]["url"],
            "assets": assets,
            "group_assignments": assignment,
        },
    )


def test_native_event_identity_units_negative_depth_and_lineage(tmp_path):
    _, _, recipe = case(tmp_path)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert sum(len(r) for r in parts.values()) == 7
    assert checks["split_check"]["valid"]
    assert checks["comcat_validation"]["one_origin_and_preferred_match_for_every_event"]
    assert checks["comcat_validation"]["missing_uncertainty_confidence_level"] == 7
    assert checks["comcat_validation"]["source_agencies"] == {"unspecified": 7}
    assert len(lineage) == 7
    assert all("target" not in row for row in parts["test"])
    union = [r for rows in parts.values() for r in rows]
    assert min(r["depth_km"] for r in union) == -0.5
    assert all(r["dmin_km"] == 0.2 * 111.195 for r in union)
    assert set(lineage[0]) == {"sample_id", "split", "event_index0", "event_id", "origin_id"}


def test_test_uncertainty_and_unused_magnitude_never_enter_inputs(tmp_path):
    tree, geo, recipe = case(tmp_path)
    before = reconstruct_comcat(recipe, tmp_path)[0]
    for event in tree.findall("b:eventParameters/b:event", NS):
        group = "cluster:" + event.get("publicID")
        if recipe["group_assignments"][group] == "test":
            event.find("b:origin/b:depth/b:uncertainty", NS).text = "90000"
    for item in geo["features"]:
        item["properties"]["mag"] = 999
    (tmp_path / "catalog.xml").write_bytes(encoded(tree))
    (tmp_path / "catalog.json").write_text(json.dumps(geo))
    assert reconstruct_comcat(recipe, tmp_path)[0] == before
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_event",
        "catalog_identity",
        "preferred_origin",
        "multiple_origins",
        "duplicate_field",
        "bad_lat",
        "bad_time",
        "noninteger_count",
        "nan",
        "wrong_namespace",
    ],
)
def test_ambiguous_or_invalid_native_sources_rejected(mutation):
    tree, _ = snapshot()
    params = tree.find("b:eventParameters", NS)
    event = params[0]
    origin = event.find("b:origin", NS)
    if mutation == "duplicate_event":
        params.append(copy.deepcopy(event))
    elif mutation == "catalog_identity":
        event.set(CAT + "eventid", "wrong")
    elif mutation == "preferred_origin":
        event.find("b:preferredOriginID", NS).text = "wrong"
    elif mutation == "multiple_origins":
        event.append(copy.deepcopy(origin))
    elif mutation == "duplicate_field":
        origin.find("b:depth", NS).append(copy.deepcopy(origin.find("b:depth/b:value", NS)))
    elif mutation == "bad_lat":
        origin.find("b:latitude/b:value", NS).text = "91"
    elif mutation == "bad_time":
        origin.find("b:time/b:value", NS).text = "2026-07-01T00:00:00"
    elif mutation == "noninteger_count":
        origin.find("b:quality/b:usedStationCount", NS).text = "12.5"
    elif mutation == "nan":
        origin.find("b:depth/b:value", NS).text = "NaN"
    elif mutation == "wrong_namespace":
        tree.tag = "quakeml"
    with pytest.raises(ValueError):
        decode_quakeml(encoded(tree))


def test_xml_entities_and_allocation_limits_fail():
    with pytest.raises(ValueError, match="XML declarations"):
        decode_quakeml(b'<!DOCTYPE x [<!ENTITY a "b">]><x/>')
    with pytest.raises(ValueError, match="bounded"):
        decode_quakeml(b"x" * 12_000_001)
    with pytest.raises(ValueError, match="bounded"):
        cluster_events([])


def test_missing_quakeml_distance_remains_missing_despite_geojson_zero():
    tree, geo = snapshot()
    quality = tree.find("b:eventParameters/b:event/b:origin/b:quality", NS)
    quality.remove(quality.find("b:minimumDistance", NS))
    geo["features"][0]["properties"]["dmin"] = 0
    rows = decode_quakeml(encoded(tree))
    cross = check_geojson(json.dumps(geo).encode(), rows, 7, "2.7.0")
    assert rows[0]["exclusion_reasons"] == ["dmin_km:missing"]
    assert cross["missingness_disagreements"] == [
        {"event_id": "us7000test0", "field": "dmin_km", "xml_missing": True, "geo_missing": False}
    ]
    assert not cross["geojson_used_to_impute_inputs"]


def test_zero_uncertainty_retained_as_an_exclusion_not_invented_error():
    tree, _ = snapshot()
    tree.find("b:eventParameters/b:event/b:origin/b:depth/b:uncertainty", NS).text = "0"
    rows = decode_quakeml(encoded(tree))
    assert rows[0]["exclusion_reasons"] == ["target:nonpositive"]
    assert rows[0]["depth_type"] is None


@pytest.mark.parametrize(
    "mutation", ["identity", "count", "service", "time", "depth", "duplicated_key"]
)
def test_cross_format_mismatch_is_not_silently_replaced(mutation):
    tree, geo = snapshot()
    rows = decode_quakeml(encoded(tree))
    if mutation == "identity":
        geo["features"][0]["id"] = "other"
    elif mutation == "count":
        geo["metadata"]["count"] = 6
    elif mutation == "service":
        geo["metadata"]["api"] = "different"
    elif mutation == "time":
        geo["features"][0]["properties"]["time"] += 1
    elif mutation == "depth":
        geo["features"][0]["geometry"]["coordinates"][2] += 1
    raw = json.dumps(geo).encode()
    if mutation == "duplicated_key":
        raw = raw.replace(b'"count": 7', b'"count": 7, "count": 7')
    with pytest.raises(ValueError):
        check_geojson(raw, rows, 7, "2.7.0")


def points():
    return [
        {
            "sid": f"event-{i}",
            "lat": 0,
            "lon": i * 0.6,
            "time": i * 6 * 86400,
            "exclusion_reasons": ["target:nonpositive"] if i == 1 else [],
        }
        for i in range(3)
    ]


def test_transitive_graph_retains_ineligible_bridge_and_source_order_invariance():
    rows = points()
    mapping, inventory, graph = cluster_events(rows)
    assert len(set(mapping.values())) == 1
    assert inventory[0]["time_span_days"] == 12
    assert inventory[0]["source_events"] == 3
    assert inventory[0]["eligible_events"] == 2
    assert graph["space_time_edges"] == 2
    assert cluster_events(list(reversed(rows)))[0] == mapping
    assert len(set(cluster_events([rows[0], rows[2]])[0].values())) == 2


def test_pair_time_boundary_distance_boundary_and_work_bound():
    rows = points()[:2]
    rows[1]["time"] = 7 * 86400
    assert cluster_events(rows)[2]["space_time_edges"] == 1
    rows[1]["time"] += 0.001
    assert cluster_events(rows)[2]["space_time_edges"] == 0
    rows[1]["time"] = 0
    rows[1]["lon"] = 1
    assert cluster_events(rows)[2]["space_time_edges"] == 0
    rows[1]["lon"] = 0.5
    with pytest.raises(ValueError, match="candidate-pair"):
        cluster_events(rows, max_pairs=0)


def test_confirmation_assignment_and_query_mutation_rejected(tmp_path):
    _, _, recipe = case(tmp_path)
    test = next(g for g, p in recipe["group_assignments"].items() if p == "test")
    train = next(g for g, p in recipe["group_assignments"].items() if p == "train")
    recipe["group_assignments"][test], recipe["group_assignments"][train] = "train", "test"
    with pytest.raises(ValueError, match="confirmation clusters"):
        reconstruct_comcat(recipe, tmp_path)
    recipe["source_query_url"] = "https://example.invalid/new-query"
    with pytest.raises(ValueError, match="Catalog query"):
        reconstruct_comcat(recipe, tmp_path)


def test_source_clock_is_explicit_utc():
    expected = datetime(2026, 7, 1, 0, 0, 0, 1000, tzinfo=UTC).timestamp()
    assert utc_timestamp("2026-07-01T00:00:00.001Z") == expected
    with pytest.raises(ValueError):
        utc_timestamp("2026-02-30T00:00:00Z")


def test_nonfinite_geojson_literals_cannot_hide_in_unused_fields():
    tree, geo = snapshot()
    geo["features"][0]["properties"]["mag"] = float("nan")
    with pytest.raises(ValueError, match="Nonfinite GeoJSON literal"):
        check_geojson(json.dumps(geo).encode(), decode_quakeml(encoded(tree)), 7, "2.7.0")


def test_time_extent_uses_actual_clock_not_iso_string_order(tmp_path):
    tree, geo, recipe = case(tmp_path)
    tree.find("b:eventParameters/b:event/b:origin/b:time/b:value", NS).text = "2026-07-01T00:00:00Z"
    geo["features"][0]["properties"]["time"] -= 1
    (tmp_path / "catalog.xml").write_bytes(encoded(tree))
    (tmp_path / "catalog.json").write_text(json.dumps(geo))
    checks = reconstruct_comcat(recipe, tmp_path)[2]
    assert checks["comcat_validation"]["source_clock_range_utc"] == [
        "2026-07-01T00:00:00Z",
        "2026-07-01T00:00:00.001Z",
    ]
