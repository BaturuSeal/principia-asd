"""Curator-only QuakeML reconstruction of catalog-reported uncertainty.

Inputs and outputs are contemporaneous location-solver products, not raw waveforms
or independently measured depth errors. GeoJSON cross-checks identity and source
fields; it never fills missing QuakeML measurements or selects scored events.
"""

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
from scipy.spatial import cKDTree

from ..io import contained, sha
from .splits import check_units

NS = {"b": "http://quakeml.org/xmlns/bed/1.2"}
CAT = "{http://anss.org/xmlns/catalog/0.1}"
FIELDS = {
    "target": "b:depth/b:uncertainty",
    "depth_km": "b:depth/b:value",
    "rms_s": "b:quality/b:standardError",
    "phases": "b:quality/b:usedPhaseCount",
    "stations": "b:quality/b:usedStationCount",
    "gap_deg": "b:quality/b:azimuthalGap",
    "dmin_km": "b:quality/b:minimumDistance",
}


def _text(node, path, *, required=False):
    values = node.findall(path, NS)
    if len(values) > 1:
        raise ValueError("Ambiguous repeated QuakeML field: " + path)
    if not values:
        if required:
            raise ValueError("Missing required QuakeML field: " + path)
        return None
    value = values[0]
    if list(value) or value.text is None or not value.text.strip() or len(value.text) > 2048:
        raise ValueError("Invalid scalar QuakeML field: " + path)
    return value.text.strip()


def _value(node, path, *, required=False):
    value = _text(node, path, required=required)
    if value is None:
        return math.nan
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite stored QuakeML value: " + path)
    return result


def utc_timestamp(value):
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", value):
        raise ValueError("QuakeML timestamp must explicitly use UTC")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def eligibility(values):
    reasons = [key + ":missing" for key, value in values.items() if not math.isfinite(value)]
    reasons += [
        key + ":nonpositive"
        for key in ("target", "rms_s", "phases", "stations")
        if math.isfinite(values[key]) and values[key] <= 0
    ]
    if math.isfinite(values["gap_deg"]) and not 0 <= values["gap_deg"] <= 360:
        reasons.append("gap_deg:outside_domain")
    if math.isfinite(values["dmin_km"]) and values["dmin_km"] < 0:
        reasons.append("dmin_km:negative")
    return reasons


def decode_quakeml(raw):
    from .native import _xml

    if len(raw) > 12_000_000:
        raise ValueError("QuakeML exceeds bounded source size")
    tree = _xml(raw)
    if tree.tag != "{http://quakeml.org/xmlns/quakeml/1.2}quakeml":
        raise ValueError("Unregistered QuakeML namespace")
    events = tree.findall("b:eventParameters/b:event", NS)
    if not 1 <= len(events) <= 5000 or len(events) != len(tree.findall(".//b:event", NS)):
        raise ValueError("Unexpected or excessive event inventory")
    rows, seen, origin_ids = [], set(), set()
    for index, event in enumerate(events):
        sid = event.get("publicID", "")
        match = re.fullmatch(
            r"quakeml:earthquake\.usgs\.gov/fdsnws/event/1/query\?eventid=([a-z0-9]+)&format=quakeml",
            sid,
        )
        if not match or sid in seen:
            raise ValueError("Invalid or duplicate QuakeML event identity")
        seen.add(sid)
        catalog_id = event.get(CAT + "eventsource", "") + event.get(CAT + "eventid", "")
        if catalog_id != match[1] or _text(event, "b:type", required=True) != "earthquake":
            raise ValueError("Event identifier or type differs from the registered catalog")
        origins = event.findall("b:origin", NS)
        if len(origins) != 1:
            raise ValueError("Historical task requires exactly one unambiguous origin")
        origin = origins[0]
        oid = origin.get("publicID", "")
        if (
            not oid
            or oid in origin_ids
            or _text(event, "b:preferredOriginID", required=True) != oid
        ):
            raise ValueError("Origin identity or preferred-origin binding is ambiguous")
        origin_ids.add(oid)
        values = {key: _value(origin, path) for key, path in FIELDS.items()}
        values["target"] /= 1000
        values["depth_km"] /= 1000
        values["dmin_km"] *= 111.195
        for key in ("phases", "stations"):
            if math.isfinite(values[key]) and not values[key].is_integer():
                raise ValueError("Noninteger source phase/station count")
        lat = _value(origin, "b:latitude/b:value", required=True)
        lon = _value(origin, "b:longitude/b:value", required=True)
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Source coordinates outside registered domain")
        timestamp_text = _text(origin, "b:time/b:value", required=True)
        rows.append(
            {
                "sid": sid,
                "event_id": catalog_id,
                "origin_id": oid,
                "event_index0": index,
                "lat": lat,
                "lon": lon,
                "time": utc_timestamp(timestamp_text),
                "time_utc": timestamp_text,
                "values": values,
                "exclusion_reasons": eligibility(values),
                "agency": _text(origin, "b:creationInfo/b:agencyID"),
                "origin_created_utc": _text(origin, "b:creationInfo/b:creationTime"),
                "confidence_level": _text(origin, "b:depth/b:confidenceLevel"),
                "depth_type": _text(origin, "b:depthType"),
            }
        )
    return rows


def check_geojson(raw, rows, count, service):
    from .native import _unique_object

    def invalid_constant(value):
        raise ValueError("Nonfinite GeoJSON literal: " + value)

    if len(raw) > 6_000_000:
        raise ValueError("GeoJSON exceeds bounded source size")
    doc = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=invalid_constant)
    if doc.get("type") != "FeatureCollection" or not isinstance(doc.get("features"), list):
        raise ValueError("Unexpected GeoJSON schema")
    meta = doc["metadata"]
    if (
        meta["count"] != count
        or len(rows) != count
        or len(doc["features"]) != count
        or meta["api"] != service
        or meta["status"] != 200
    ):
        raise ValueError("Source count or service-version records disagree")
    features = {feature["id"]: feature for feature in doc["features"]}
    if len(features) != count or set(features) != {row["event_id"] for row in rows}:
        raise ValueError("GeoJSON/QuakeML event identities differ or repeat")
    missingness = []
    for row in rows:
        feature = features[row["event_id"]]
        prop, geom = feature["properties"], feature["geometry"]
        if feature["type"] != "Feature" or geom["type"] != "Point" or len(geom["coordinates"]) != 3:
            raise ValueError("Unsupported GeoJSON geometry")
        values = row["values"]
        comparisons = {
            "lat": (row["lat"], geom["coordinates"][1]),
            "lon": (row["lon"], geom["coordinates"][0]),
            "depth_km": (values["depth_km"], geom["coordinates"][2]),
            "stations": (values["stations"], prop["nst"]),
            "rms_s": (values["rms_s"], prop["rms"]),
            "gap_deg": (values["gap_deg"], prop["gap"]),
            "dmin_km": (
                values["dmin_km"],
                None if prop["dmin"] is None else float(prop["dmin"]) * 111.195,
            ),
        }
        if not math.isclose(row["time"] * 1000, prop["time"], rel_tol=0, abs_tol=0.001):
            raise ValueError("Event time differs across source representations")
        for key, (xml, geo) in comparisons.items():
            if not math.isfinite(xml) or geo is None:
                if not math.isfinite(xml) and geo is None:
                    continue
                missingness.append(
                    {
                        "event_id": row["event_id"],
                        "field": key,
                        "xml_missing": not math.isfinite(xml),
                        "geo_missing": geo is None,
                    }
                )
            elif not math.isclose(xml, float(geo), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("Numeric source representations disagree: " + key)
    return {
        "events": count,
        "exact_event_identity_join": True,
        "source_generated_epoch_ms": meta["generated"],
        "source_query_url": meta["url"],
        "service_version": service,
        "missingness_disagreements": missingness,
        "geojson_used_to_impute_inputs": False,
    }


def cluster_events(rows, *, max_pairs=2_000_000):
    if not rows or len(rows) > 5000:
        raise ValueError("Event graph exceeds bounded allocation")
    lat, lon = np.deg2rad([[r["lat"], r["lon"]] for r in rows]).T
    xyz = (
        np.column_stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]) * 6371
    )
    tree = cKDTree(xyz)
    parent = list(range(len(rows)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    candidates, edges = 0, 0
    # Bounded per-point neighborhoods avoid an unbounded all-pairs set allocation.
    for i, point in enumerate(xyz):
        for j in tree.query_ball_point(point, 100):
            if j <= i:
                continue
            candidates += 1
            if candidates > max_pairs:
                raise ValueError("Event graph exceeds bounded candidate-pair work")
            if abs(rows[i]["time"] - rows[j]["time"]) <= 7 * 86400:
                u, v = find(i), find(j)
                parent[max(u, v)] = min(u, v)
                edges += 1
    clusters = defaultdict(list)
    for i in range(len(rows)):
        clusters[find(i)].append(i)
    mapping, inventory = {}, []
    for indices in clusters.values():
        name = "cluster:" + min(rows[i]["sid"] for i in indices)
        for i in indices:
            mapping[rows[i]["sid"]] = name
        inventory.append(
            {
                "group": name,
                "event_indices0": indices,
                "event_ids_sha256": sha(sorted(rows[i]["sid"] for i in indices)),
                "source_events": len(indices),
                "eligible_events": sum(not rows[i]["exclusion_reasons"] for i in indices),
                "time_span_days": (
                    max(rows[i]["time"] for i in indices) - min(rows[i]["time"] for i in indices)
                )
                / 86400,
            }
        )
    return (
        mapping,
        sorted(inventory, key=lambda item: item["group"]),
        {
            "candidate_spatial_pairs": candidates,
            "space_time_edges": edges,
            "source_clusters": len(clusters),
            "threshold_distance_km": 100,
            "distance_definition": "Euclidean chord of a 6371km sphere, not surface arc length",
            "threshold_time_days": 7,
            "transitive_components_before_eligibility": True,
        },
    )


def source_test_groups(groups):
    def key(group):
        raw = ("principia100-batch7:quake:" + group).encode()
        return int(hashlib.sha256(raw).hexdigest()[:16], 16)

    ordered = sorted(groups, key=key)
    return set(ordered[: max(1, len(ordered) // 5)])


def reconstruct_comcat(recipe, source_root):
    from .native import _registered_groups, _row, identity

    def asset(role):
        (item,) = [a for a in recipe["assets"] if a["role"] == role]
        return item, contained(source_root, item["path"])

    xml_asset, xml = asset("quakeml_catalog")
    _, geo = asset("geojson_catalog")
    _, count = asset("catalog_count")
    _, service = asset("catalog_service_version")
    rows = decode_quakeml(xml.read_bytes())
    cross = check_geojson(
        geo.read_bytes(), rows, int(count.read_text()), service.read_text().strip()
    )
    if cross["source_query_url"] != recipe["source_query_url"]:
        raise ValueError("Catalog query differs from registered source snapshot")
    mapping, inventory, graph = cluster_events(rows)
    eligible = [r for r in rows if not r["exclusion_reasons"]]
    groups = {mapping[r["sid"]] for r in eligible}
    assignments = _registered_groups(recipe, groups)
    held = source_test_groups(set(mapping.values()))
    if {g for g, split in assignments.items() if split == "test"} != held & groups:
        raise ValueError("Historical confirmation clusters differ from metadata allocation")
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    for event in eligible:
        group = mapping[event["sid"]]
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        values = event["values"]
        row, source = _row(
            recipe["scenario_id"],
            event["sid"],
            group,
            split,
            {k: v for k, v in values.items() if k != "target"},
            values["target"],
            {
                "event_index0": event["event_index0"],
                "event_id": event["event_id"],
                "origin_id": event["origin_id"],
            },
        )
        parts[split].append(row)
        lineage.append(source)
    exclusions = [
        {
            "event_index0": r["event_index0"],
            "event_id": r["event_id"],
            "reasons": r["exclusion_reasons"],
        }
        for r in rows
        if r["exclusion_reasons"]
    ]
    reasons = Counter(reason for r in exclusions for reason in r["reasons"])
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "comcat_validation": {
                "catalog_events": len(rows),
                "eligible_events": len(eligible),
                "excluded_events": len(exclusions),
                "exclusion_counts": dict(sorted(reasons.items())),
                "one_origin_and_preferred_match_for_every_event": True,
                "missing_uncertainty_confidence_level": sum(
                    r["confidence_level"] is None for r in rows
                ),
                "missing_depth_type": sum(r["depth_type"] is None for r in rows),
                "source_agencies": dict(
                    sorted(Counter(r["agency"] or "unspecified" for r in rows).items())
                ),
                "source_clock_range_utc": [
                    min(rows, key=lambda row: row["time"])["time_utc"],
                    max(rows, key=lambda row: row["time"])["time_utc"],
                ],
                "eligible_clusters": len(groups),
                "empty_eligible_clusters": len(inventory) - len(groups),
                "largest_source_cluster": max(c["source_events"] for c in inventory),
                "cross_format_missingness_disagreements": len(cross["missingness_disagreements"]),
                "fitting_performed": False,
            },
            "source_archive": xml_asset["path"],
            "quantity_paths": FIELDS,
            "field_classification": "depth and uncertainty are source-fitted location quantities; RMS is a source fit diagnostic; phase/station counts and station geometry are supporting derived metadata",
            "source_format_cross_check": cross,
            "cluster_policy": graph,
            "cluster_inventory": inventory,
            "excluded_events": exclusions,
            "independence_scope": "Whole transitive components; networks and velocity-model systematics may remain shared across partitions. No temporal or network transfer claim.",
            "response_scope": "Author-reported depth uncertainty, not independently measured depth error or a prespecified confidence interval. Diagnostic retrospective task only.",
            "recommended_edition_role": "diagnostic_pending_scientific_review",
            "admission_blockers": [
                "Scientific review must distinguish catalog-solver emulation from independently supported discovery",
                "Reported uncertainty lacks an explicit confidence level and is not an independent error observation",
                "Contributor rights/notices, network dependence and perturbation standards remain pending",
            ],
        },
    )
