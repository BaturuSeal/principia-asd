"""Native curator readers for versioned equation tasks, never discovery-agent readers.

No fitting, test-based selection or downloaded executable code. Complete native
coordinates and explicit exclusions accompany every deterministic projection.
"""

import csv
import math
import re
import zipfile
from collections import Counter
from pathlib import PurePosixPath

import numpy as np

from ..io import file_sha
from .native import NS, REL, _xml


def workbook_cells(path, sheet_name):
    """Read stored scalar cells only. Formula cells are flagged, not evaluated."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or sum(x.file_size for x in z.infolist()) > 12_000_000:
            raise ValueError("Oversized or duplicate workbook members")
        if any(PurePosixPath(x).is_absolute() or ".." in PurePosixPath(x).parts for x in names):
            raise ValueError("Unsafe workbook path")
        sheets = _xml(z.read("xl/workbook.xml")).findall(f"{NS}sheets/{NS}sheet")
        matches = [s for s in sheets if s.get("name") == sheet_name]
        if len(matches) != 1:
            raise ValueError("Ambiguous worksheet")
        relationships = [
            x
            for x in _xml(z.read("xl/_rels/workbook.xml.rels"))
            if x.get("Id") == matches[0].get(REL + "id")
        ]
        if len(relationships) != 1 or relationships[0].get("TargetMode") == "External":
            raise ValueError("Unresolved worksheet")
        target = PurePosixPath(relationships[0].get("Target", ""))
        if target.is_absolute() or ".." in target.parts:
            raise ValueError("Unsafe worksheet relationship")
        strings = (
            [
                "".join(t.text or "" for t in x.iter(NS + "t"))
                for x in _xml(z.read("xl/sharedStrings.xml")).findall(NS + "si")
            ]
            if "xl/sharedStrings.xml" in names
            else []
        )
        cells, formulas = {}, set()
        for cell in _xml(z.read("xl/" + str(target))).iter(NS + "c"):
            key = cell.get("r")
            if key in cells or not re.fullmatch(r"[A-Z]+[1-9][0-9]*", key or ""):
                raise ValueError("Duplicate or invalid cell identity")
            if cell.find(NS + "f") is not None:
                formulas.add(key)
            value = cell.findtext(NS + "v")
            kind = cell.get("t", "n")
            if kind == "s":
                value = strings[int(value)]
            elif kind == "inlineStr":
                value = "".join(t.text or "" for t in cell.iter(NS + "t"))
            elif kind not in {"n", "str"}:
                raise ValueError("Unsupported cell type")
            cells[key] = value
        return cells, formulas


def number(cells, formulas, address):
    if address in formulas:
        raise ValueError("A required measurement is a workbook formula: " + address)
    value = float(cells[address])
    if not math.isfinite(value):
        raise ValueError("Nonfinite native measurement: " + address)
    return value


def source(path, root):
    return {
        "path": str(path.relative_to(root)),
        "sha256": file_sha(path),
        "bytes": path.stat().st_size,
    }


def item(sid, group, partition, coordinate, values, target):
    return dict(
        sample_id=f"{sid}:{coordinate}",
        group=group,
        partition=partition,
        source_coordinate=coordinate,
        **values,
        target=float(target),
    )


def cure(root):
    paths = [root / "raw/Figure 1-Conversion rate.xlsx", root / "raw/Figure 2-Conversion.xlsx"]
    rate, rf = workbook_cells(paths[0], "Figure1")
    conv, cf = workbook_cells(paths[1], "Figure2")
    rows, excluded = [], []
    for tcol, vcol, beta, part in [
        ("A", "B", 1, "train"),
        ("E", "F", 3, "dev"),
        ("I", "J", 5, "train"),
        ("M", "N", 10, "train"),
        ("Q", "R", 20, "test"),
    ]:
        if (
            rate[tcol + "1"] != f"{beta:.1f} °C/min"
            or rate[vcol + "2"] != "Conversion Rate (%/min)"
            or conv[vcol + "2"] != "Conversion"
        ):
            raise ValueError("Changed cure source headers")
        group = f"heating-{beta}C-min"
        indices = sorted(
            int(k[len(tcol) :])
            for k in rate
            if re.fullmatch(tcol + r"[0-9]+", k) and int(k[len(tcol) :]) > 2
        )
        for i in indices:
            raw_temp = rate.get(f"{tcol}{i}")
            if raw_temp is None or not str(raw_temp).strip() or set(str(raw_temp).strip()) == {"-"}:
                excluded.append({"coordinate": f"{tcol}{i}", "reason": "native_blank_or_separator"})
                continue
            temp = number(rate, rf, f"{tcol}{i}")
            if temp != number(conv, cf, f"{tcol}{i}"):
                raise ValueError("Conversion and rate temperatures do not align")
            alpha = number(conv, cf, f"{vcol}{i}")
            if not -0.05 <= alpha <= 1.05:
                excluded.append(
                    {"coordinate": f"{tcol}{i}", "reason": "conversion_outside_fraction_domain"}
                )
                continue
            rows.append(
                item(
                    "013",
                    group,
                    part,
                    f"Figure1+2:{tcol}{i}:{vcol}{i}",
                    {"temperature": temp + 273.15, "conversion": alpha, "heating_rate": beta / 60},
                    number(rate, rf, f"{vcol}{i}") / 6000,
                )
            )
    return rows, excluded, [source(x, root) for x in paths]


def membrane(root):
    path = root / "raw/DataPorousMembranes.xlsx"
    cells, formulas = workbook_cells(path, "Porous membranes - fitting")
    if [cells[x] for x in ["H6", "H7", "I7", "J7", "K7", "L7"]] != [
        "S-HT",
        "gas",
        "T",
        "p(perm)",
        "p(ret)",
        "flux",
    ]:
        raise ValueError("Unexpected membrane identity or columns")
    if [cells[x] for x in ["I8", "J8", "K8", "L8"]] != ["°C", "bar(a)", "bar(a)", "mol s-1 m-2"]:
        raise ValueError("Unexpected membrane units")
    rows, excluded = [], []
    for i in range(9, max(int(re.search(r"\d+", k)[0]) for k in cells) + 1):
        gas = cells.get(f"H{i}")
        if gas != "N2":
            excluded.append({"coordinate": f"H{i}:L{i}", "reason": "not_pure_nitrogen_task"})
            continue
        temp = number(cells, formulas, f"I{i}")
        nominal = min([25, 200, 300, 350, 400, 450, 500], key=lambda x: abs(x - temp))
        if abs(nominal - temp) > 8:
            raise ValueError("Unregistered membrane temperature regime")
        part = "dev" if nominal == 350 else "test" if nominal in [300, 400, 450] else "train"
        feed, perm = (
            number(cells, formulas, f"K{i}") * 100000,
            number(cells, formulas, f"J{i}") * 100000,
        )
        target = number(cells, formulas, f"L{i}")
        if not (feed > perm > 0 and temp > -273.15 and target > 0):
            excluded.append({"coordinate": f"H{i}:L{i}", "reason": "invalid_transport_domain"})
            continue
        rows.append(
            item(
                "061",
                f"S-HT-N2-{nominal}C",
                part,
                f"Porous membranes - fitting:H{i}:L{i}",
                {"temperature": temp + 273.15, "pressure_feed": feed, "pressure_permeate": perm},
                target,
            )
        )
    return rows, excluded, [source(path, root)]


def thermal(root):
    rows, excluded, sources = [], [], []
    for path in sorted((root / "raw").rglob("*.csv")):
        rel = str(path.relative_to(root / "raw"))
        with path.open() as f:
            if next(f).strip() != "t,T_L,T_H,T_E,theta_dot,tau_f":
                raise ValueError("Unknown gearbox channels")
        values = np.loadtxt(path, delimiter=",", skiprows=1)
        if (
            values.ndim != 2
            or values.shape[1] != 6
            or not np.isfinite(values).all()
            or (np.diff(values[:, 0]) <= 0).any()
        ):
            raise ValueError("Invalid gearbox clock or native values")
        part = (
            "test" if rel.startswith("validation/") else "dev" if "1p4137" in path.name else "train"
        )
        sources.append(source(path, root))
        # Nonoverlapping one-minute forecasts. Inputs are sampled at the start,
        # never averaged from the future or taken from filename desired velocities.
        starts = np.arange(values[0, 0], values[-1, 0] - 60, 60)
        for aim in starts:
            a, b = np.searchsorted(values[:, 0], [aim, aim + 60])
            if (
                b >= len(values)
                or max(abs(values[a, 0] - aim), abs(values[b, 0] - aim - 60)) > 0.02
            ):
                excluded.append(
                    {"coordinate": f"{rel}:{aim}", "reason": "no_exact_60s_pair_within_20ms"}
                )
                continue
            t, tl, th, te, speed, torque = values[a]
            rows.append(
                item(
                    "069",
                    rel,
                    part,
                    f"{rel}:rows{a + 2}-{b + 2}",
                    {
                        "lubricant_temperature": tl + 273.15,
                        "housing_temperature": th + 273.15,
                        "environment_temperature": te + 273.15,
                        "speed": speed,
                        "torque": torque,
                        "horizon": values[b, 0] - t,
                    },
                    values[b, 1] - tl,
                )
            )
    return rows, excluded, sources


def soil(root):
    path = root / "raw/holisoils_soil_respiration_dataset.csv"
    dev = {"Llobera", "Secanella", "St Christol"}
    test = {"Gamiz", "Kacergine", "Kranzberg-Freising", "Saint Mitre", "RincondelBatovi"}
    rows, excluded = [], []
    with path.open(newline="") as f:
        for i, r in enumerate(csv.DictReader(f), 2):
            try:
                temp, water, flux = (float(r[k]) for k in ["t05", "tsmoisture", "flux"])
            except ValueError:
                excluded.append({"row": i, "reason": "missing_required_native_measurement"})
                continue
            if not (
                all(math.isfinite(x) for x in [temp, water, flux])
                and -50 < temp < 70
                and 0 <= water <= 100
                and r["trenched"] in {"True", "False"}
            ):
                excluded.append(
                    {"row": i, "reason": "invalid_temperature_water_or_trenching_metadata"}
                )
                continue
            site = r["siteid"]
            # Adjacent experimental site families never cross a partition.
            group = (
                "Dumbravita"
                if site.startswith("Dumbravita")
                else "Karstula"
                if site.startswith("Karstula")
                else site
            )
            part = "dev" if site in dev else "test" if site in test else "train"
            row = item(
                "082",
                group,
                part,
                f"holisoils_soil_respiration_dataset.csv:{i}",
                {
                    "temperature": temp + 273.15,
                    "water_fraction": water / 100,
                    "root_exclusion": int(r["trenched"] == "True"),
                },
                flux * 0.001 / 3600,
            )
            row["observation_identity"] = "|".join(
                r[k] for k in ["siteid", "date", "subsiteid", "point"]
            )
            rows.append(row)
    counts = Counter(r["observation_identity"] for r in rows)
    # Repeated acquisitions remain separate source rows, but retain their common site.
    for r in rows:
        r["repeated_identity"] = counts[r["observation_identity"]] > 1
    return rows, excluded, [source(path, root)]


READERS = {"013": cure, "061": membrane, "069": thermal, "082": soil}
