"""Native-format fixtures verify custody and whole-experiment partitions."""

import importlib.util
import zipfile
from pathlib import Path

import pytest

from principia_asd.io import read_csv, read_json, write_json
from principia_asd.web.server import App

spec = importlib.util.spec_from_file_location(
    "prepare_equation_pack", Path(__file__).parents[1] / "scripts/prepare_equation_pack.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def native_sources(root):
    registry = []
    for case in ["048", "057", "058"]:
        registry.append(
            dict(
                case_id="P100-" + case,
                local_folder="source-" + case,
                domain="fixture",
                source_url="https://example.org/" + case,
                license_or_terms="fixture",
                independent_units="native test groups",
            )
        )
    write_json(root / "_benchmark_100/CATALOG.json", registry)
    for filename, month in [("dra26001.dat", 1), ("dra26182.dat", 7), ("psu26001.dat", 1)]:
        path = root / "source-048/raw" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        a = ["0"] * 48
        for i, v in {0: 2026, 1: 1, 2: month, 3: 1, 4: 12, 5: 0, 16: 300, 38: 20, 40: 50}.items():
            a[i] = str(v)
        b = list(a)
        b[5] = "1"
        path.write_text("station\nmetadata\n" + " ".join(a) + "\n" + " ".join(b) + "\n")
    path = root / "source-057/raw/Rheological_Data_For_Syntactic_Foam.zip"
    path.parent.mkdir(parents=True)
    with zipfile.ZipFile(path, "w") as archive:
        for suffix in ["", " 1", " 2", " 3", " 4"]:
            content = "Interval data:\tPoint No.\tTemperature\tViscosity\tStatus\tShear Rate\tRotational Speed\n\t1\t35\t1000\tDy_auto\t2\t1\n\t2\t35\t-2\tDy_auto\t2\t1\n"
            archive.writestr(
                "fixture/Neat_Resin Viscosity" + suffix + ".csv", content.encode("utf-16")
            )
    path = root / "source-058/raw/PDLLA15k_DSC_GPC_rheo.zip"
    path.parent.mkdir(parents=True)
    with zipfile.ZipFile(path, "w") as archive:
        for temp in range(40, 81, 5):
            content = "w\tG'\tG\"\ttan(d)\th*\tTorque\tg\td\nrad/s\tPa\tPa\t \tPa-s\tg-cm\t%\t°\n1\t20\t10\t0.5\t20\t1\t1\t1\n"
            archive.writestr(
                f"fixture/rheology/DFS_gap0.879_T{temp}_smax1", content.encode("latin1")
            )


def test_native_mapping_units_group_separation_lineage_and_private_targets(tmp_path):
    native_sources(tmp_path / "raw")
    output, vault = tmp_path / "public", tmp_path / "private"
    receipts = builder.prepare(tmp_path / "raw", output, vault)
    assert len(receipts) == 3
    for audit in receipts:
        root = output / "scenarios" / audit["scenario_id"]
        t = read_json(root / "task-contracts/task-001.json")
        train, dev, test = [read_csv(root / t["split"][k]) for k in ["train", "dev", "test"]]
        assert all("target" not in r for r in test)
        assert all("target" in r for r in train + dev)
        group_sets = [{r["group"] for r in a} for a in [train, dev, test]]
        assert all(not group_sets[i] & group_sets[j] for i, j in [(0, 1), (0, 2), (1, 2)])
        assert len(read_csv(root / "provenance/lineage.csv.gz")) == len(train + dev + test)
        targets = read_csv(vault / audit["scenario_id"] / "test_targets.csv.gz")
        assert {r["sample_id"] for r in test} == {r["sample_id"] for r in targets}
    resin = read_csv(output / "scenarios/P100-057/public/train.csv.gz")
    assert resin[0]["target"] == 1 and resin[0]["temperature"] == 308.15
    assert len(read_json(vault / "P100-057/excluded-records.json")) == 5
    polymer = read_csv(output / "scenarios/P100-058/public/train.csv.gz")
    assert {r["response_kind"] for r in polymer} == {0, 1}
    assert len({r["group"] for r in polymer}) == 5
    app = App({"workspace": str(tmp_path / "workspace"), "data_root": str(output)})
    catalog = app.catalog()
    assert len(catalog) == 3
    assert all(s["size"]["expanded_public_bytes"] > s["size"]["public_bytes"] for s in catalog)
    assert all("explicit units" in s["representation"] for s in catalog)
    # The script refuses to rewrite an edition, even when raw inputs are identical.
    with pytest.raises(ValueError, match="immutable"):
        builder.prepare(tmp_path / "raw", output, vault)
