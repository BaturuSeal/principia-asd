"""Explicit scientific split checks, separate from scoring groups and inference."""

import math
from collections import defaultdict

PARTITIONS = ("train", "dev", "test")


def check_units(partitions, group_to_unit):
    """An aggregation group is not necessarily an independent split unit."""
    membership = defaultdict(set)
    missing = set()
    for split in PARTITIONS:
        for row in partitions[split]:
            group = row["group"]
            if group not in group_to_unit:
                missing.add(group)
            else:
                membership[group_to_unit[group]].add(split)
    overlaps = {unit: sorted(splits) for unit, splits in sorted(membership.items())
                if len(splits) > 1}
    return {"valid": not missing and not overlaps,
            "unmapped_groups": sorted(missing), "shared_split_units": overlaps,
            "units_by_partition": {p: sorted(u for u, splits in membership.items() if p in splits)
                                   for p in PARTITIONS}}


def check_chronology(partitions, *, time_column, stream_columns):
    """Require strictly ordered, nonempty train/dev/test windows in every stream."""
    if not stream_columns:
        raise ValueError("Explicit stream columns are required")
    times = defaultdict(lambda: defaultdict(list))
    for split in PARTITIONS:
        for row in partitions[split]:
            t = float(row[time_column])
            if not math.isfinite(t):
                raise ValueError("Nonfinite observation time")
            stream = tuple(row[k] for k in stream_columns)
            times[stream][split].append(t)
    results = []
    for stream, groups in sorted(times.items()):
        intervals = {p: {"min": min(ts), "max": max(ts), "rows": len(ts)}
                     for p, ts in groups.items()}
        violations = []
        for earlier, later in zip(PARTITIONS, PARTITIONS[1:], strict=False):
            if earlier not in groups or later not in groups:
                violations.append(f"Missing {earlier} or {later} observations")
            elif max(groups[earlier]) >= min(groups[later]):
                violations.append(f"{earlier} observations are not strictly before {later}")
        results.append({"stream": dict(zip(stream_columns, stream, strict=True)),
                        "intervals": intervals, "violations": violations})
    return {"valid": bool(results) and all(not r["violations"] for r in results),
            "time_column": time_column, "stream_columns": list(stream_columns), "streams": results}


def repartition_development(partitions, development_groups):
    """Move complete groups only; preserve the original test list and all values."""
    combined = partitions["train"] + partitions["dev"]
    train = [r for r in combined if r["group"] not in development_groups]
    dev = [r for r in combined if r["group"] in development_groups]
    if not train or not dev or not development_groups <= {r["group"] for r in combined}:
        raise ValueError("Invalid development group assignment")
    return {"train": train, "dev": dev, "test": partitions["test"]}


def latest_development_groups(partitions, *, time_column, stream_columns):
    """Reserve the last complete development group per explicitly named stream."""
    grouped = defaultdict(lambda: defaultdict(list))
    group_streams = defaultdict(set)
    for row in partitions["train"] + partitions["dev"]:
        stream = tuple(row[k] for k in stream_columns)
        t = float(row[time_column])
        if not math.isfinite(t):
            raise ValueError("Nonfinite observation time")
        grouped[stream][row["group"]].append(t)
        group_streams[row["group"]].add(stream)
    if any(len(streams) != 1 for streams in group_streams.values()):
        raise ValueError("A temporal block crosses stream identities")
    selected = set()
    for groups in grouped.values():
        if len(groups) < 2:
            raise ValueError("Need at least two complete development blocks per stream")
        ordered = sorted(groups, key=lambda g: (min(groups[g]), max(groups[g]), g))
        if any(max(groups[a]) >= min(groups[b]) for a, b in zip(ordered, ordered[1:], strict=False)):
            raise ValueError("Development blocks overlap in time")
        selected.add(ordered[-1])
    return selected
