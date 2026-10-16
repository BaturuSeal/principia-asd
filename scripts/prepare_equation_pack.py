"""Reconstruct a separate local scientific scenario pack from registered native data.

No historical data, package, evaluator or leaderboard is modified. This script never
fits a model. Every native row has an inclusion/exclusion receipt and source coordinate.
"""

from __future__ import annotations

import argparse
import collections
import math
import re
import shutil
import zipfile
from pathlib import Path

from principia_asd.engine.scientific_templates import (
    atmosphere_templates,
    relaxation_templates,
    resin_templates,
)
from principia_asd.io import file_sha, read_json, sha, write_csv, write_json


def prepare(raw, output, vault):
    registry = {x["case_id"]: x for x in read_json(raw / "_benchmark_100/CATALOG.json")}
    if output.exists() or vault.exists():
        raise ValueError("Choose new output and vault directories; scenario editions are immutable")
    output.mkdir(parents=True)
    vault.mkdir(parents=True)
    receipts = []

    def package(
        case,
        title,
        description,
        inputs,
        units,
        meanings,
        rows,
        rejected,
        sources,
        templates,
        limitations,
        split_policy,
        preprocessing,
    ):
        sid = "P100-" + case
        source = registry[sid]
        root = output / "scenarios" / sid
        task = {
            "scenario_id": sid,
            "task_id": f"{sid}.equations-v1",
            "revision": 1,
            "title": title,
            "display_title": title,
            "description": description,
            "inputs": inputs,
            "output": "target",
            "quantity_units": units,
            "units": units,
            "variable_descriptions": meanings,
            "split": {
                k: f"public/{'test_inputs' if k == 'test' else k}.csv.gz"
                for k in ["train", "dev", "test"]
            },
            "metric": {
                "primary": "mae" if case == "048" else "log_mae",
                "aggregation": "equal_group_mean",
            },
            "positive_prediction": True,
            "test_exposure": "retrospective-open-test",
            "stability": {
                "domain": "Observed training ranges; positive physical quantities",
                "ranking": False,
                "relative_noise": 0.01,
                "scope": "Diagnostic input sensitivity; no calibrated measurement-error model",
                "categorical_inputs": ["response_kind"] if case == "058" else [],
            },
            "equation_templates": templates,
            "scientific_scope": "Local scientific-method development; no independent-discovery claim",
            "split_policy": split_policy,
            "preprocessing": preprocessing,
        }
        partitions = {
            k: [
                {a: b for a, b in r.items() if a != "partition"}
                for r in rows
                if r["partition"] == k
            ]
            for k in ["train", "dev", "test"]
        }
        fields = ["sample_id", "group", *inputs, "target"]
        for k, data in partitions.items():
            if not data:
                raise ValueError("Empty partition")
            public = [{f: r[f] for f in fields if k != "test" or f != "target"} for r in data]
            write_csv(root / task["split"][k], public, list(public[0]))
        targets = [
            {"sample_id": r["sample_id"], "group": r["group"], "target": r["target"]}
            for r in partitions["test"]
        ]
        custody = vault / sid
        write_csv(custody / "test_targets.csv.gz", targets, list(targets[0]))
        write_json(root / "task-contracts/task-001.json", task, immutable=True)
        write_json(
            custody / "evaluator-manifest.json",
            {
                "task_id": task["task_id"],
                "scenario_id": sid,
                "input_sha256": file_sha(root / task["split"]["test"]),
                "target_sha256": file_sha(custody / "test_targets.csv.gz"),
                "contract_sha256": file_sha(root / "task-contracts/task-001.json"),
                "version": "equation-assessment-v1",
            },
            immutable=True,
        )
        lineage = [
            {
                k: r[k]
                for k in [
                    "sample_id",
                    "group",
                    "source_file",
                    "source_line",
                    "source_channel",
                    "quality",
                ]
            }
            for r in rows
        ]
        write_csv(root / "provenance/lineage.csv.gz", lineage, list(lineage[0]))
        write_json(custody / "excluded-records.json", rejected, immutable=True)
        groups = {k: sorted({r["group"] for r in values}) for k, values in partitions.items()}
        if any(
            set(groups[a]) & set(groups[b])
            for a, b in [("train", "dev"), ("train", "test"), ("dev", "test")]
        ):
            raise ValueError("Group leakage")
        audit = {
            "scenario_id": sid,
            "included": len(rows),
            "excluded": len(rejected),
            "exclusion_reasons": dict(collections.Counter(r["reason"] for r in rejected)),
            "groups": groups,
            "split_policy": split_policy,
            "sources": sources,
            "partition_hashes": {k: file_sha(root / task["split"][k]) for k in partitions},
            "test_targets_public": False,
            "units_checked": True,
            "admission": "local_research_preview",
            "review_scope": "Native format, source units, known invalid readings, identity/group separation and reproducible preparation checked; external scientific review not assessed",
        }
        write_json(root / "provenance/preparation.json", audit, immutable=True)
        info = {
            "scenario_id": sid,
            "title": title,
            "description": description,
            "domain": source["domain"],
            "edition": "equation-pack-v1",
            "status": "local_research_preview",
            "local_extension": True,
            "rows": {k: len(v) for k, v in partitions.items()},
            "limitations": limitations,
            "independent_unit": source["independent_units"],
            "rights_status": "source_terms_documented",
            "source": {
                "url": source["source_url"],
                "license": source["license_or_terms"],
                "registry_identity": sid,
                "local_folder": source["local_folder"],
                "registry_entry_sha256": sha(source),
                "evidence": [
                    {
                        "record": source["source_url"],
                        "license": source["license_or_terms"],
                        "scope": "Registered source terms, verified against source record; no external review claim",
                    }
                ],
            },
            "size": {"public_bytes": sum(p.stat().st_size for p in root.rglob("*") if p.is_file())},
        }
        write_json(root / "scenario.json", info, immutable=True)
        (root / "README.md").write_text(
            f"# {title}\n\n{description}\n\n## Evidence and custody\n\n"
            + "\n".join("- " + x for x in limitations)
            + f"\n\nSource: {source['source_url']}\n\nLicense: {source['license_or_terms']}\n\n"
            + "The source record and acquisition hashes are in `provenance/preparation.json`. The deterministic pack builder uses the registry identity and native headers. Public test files contain inputs only; test targets and excluded native records remain in the separate private evaluator. Known equations are disclosed search priors, not discoveries.\n"
        )
        write_json(
            root / "checksums.json",
            {str(p.relative_to(root)): file_sha(p) for p in sorted(root.rglob("*")) if p.is_file()},
            immutable=True,
        )
        receipts.append(audit | {"title": title, "rows": info["rows"]})

    # P100-048: source-documented zero-based column positions and zero QC flags.
    r = raw / registry["P100-048"]["local_folder"]
    rows, rejected, sources = [], [], []
    for path in sorted((r / "raw").rglob("*.dat")):
        rel = str(path.relative_to(r))
        sources.append({"path": rel, "sha256": file_sha(path)})
        for line, text in enumerate(path.read_text().splitlines()[2:], 3):
            a = text.split()
            if len(a) != 48:
                raise ValueError("Unexpected SURFRAD native schema")
            if int(a[5]) != 0:  # Fixed hourly observations, not a learned aggregation.
                rejected.append({"file": rel, "line": line, "reason": "fixed_hourly_sampling"})
                continue
            temp, rh, target = float(a[38]), float(a[40]), float(a[16])
            if any(int(a[i]) != 0 for i in [17, 39, 41]) or not (
                -80 < temp < 60 and 0 < rh <= 100 and target > 0
            ):
                rejected.append(
                    {"file": rel, "line": line, "reason": "source_QC_or_physical_domain"}
                )
                continue
            vapor = 610.78 * math.exp(17.27 * temp / (temp + 237.3)) * rh / 100
            part = "test" if path.name.startswith("psu") else "train" if int(a[2]) == 1 else "dev"
            rows.append(
                dict(
                    sample_id=f"{path.stem}-{a[4]}00",
                    group=path.stem,
                    temperature=temp + 273.15,
                    vapor_pressure=vapor,
                    target=target,
                    partition=part,
                    source_file=rel,
                    source_line=line,
                    source_channel="downwelling_infrared[16]",
                    quality="QC 0 for temperature, RH and downwelling IR",
                )
            )
    package(
        "048",
        "Atmospheric longwave radiation across climates",
        "Surface observations from Desert Rock and Penn State test whether air temperature and humidity explain downward thermal radiation. Competing equations separate blackbody emission from effective sky emissivity; clouds and vertical structure remain unresolved.",
        ["temperature", "vapor_pressure"],
        {"temperature": "K", "vapor_pressure": "Pa", "target": "W/m2"},
        {
            "temperature": "Measured near-surface air temperature, converted to Kelvin",
            "vapor_pressure": "Derived water-vapor partial pressure from simultaneous relative humidity and air temperature; Tetens approximation",
            "target": "Measured downward longwave irradiance from the pyrgeometer",
        },
        rows,
        rejected,
        sources,
        atmosphere_templates(),
        [
            "Retrospective observations; no unseen-data claim",
            "Two sites only: the test set is site transfer to Penn State, not independent replication across many climates",
            "All retained weather conditions are included; the clear-sky-inspired prior may fail under clouds",
            "Hourly point selection and QC exclusions are completely recorded; no target-based outlier filtering",
            "Tetens saturation pressure is a disclosed deterministic preprocessing prior",
        ],
        "Train: Desert Rock January; development: Desert Rock July; test: all retained Penn State January/July days. Whole site-day blocks remain together.",
        [
            "Keep minute 00 only",
            "Require QC=0 for target, temperature and RH",
            "Celsius to Kelvin",
            "vapor_pressure = RH/100 * 610.78 * exp(17.27*T_C/(T_C+237.3)); Pa",
            "No fitted preprocessing",
        ],
    )

    # P100-057: preserve raw exported instrument readings, including explicit exclusions.
    r = raw / registry["P100-057"]["local_folder"]
    path = r / "raw/Rheological_Data_For_Syntactic_Foam.zip"
    rows, rejected = [], []
    with zipfile.ZipFile(path) as archive:
        files = sorted(f for f in archive.namelist() if f.endswith(".csv") and "/Neat_Resin" in f)
        if len(files) != 5:
            raise ValueError("Unexpected neat-resin replicate inventory")
        for f in files:
            match = re.search(r"Viscosity (\d)\.csv", f)
            replicate = int(match[1]) if match else 0
            part = "train" if replicate < 3 else "dev" if replicate == 3 else "test"
            block = 0
            for line, text in enumerate(archive.read(f).decode("utf-16").splitlines(), 1):
                if text.startswith("Interval data:"):
                    if text.split("\t")[1:4] != ["Point No.", "Temperature", "Viscosity"]:
                        raise ValueError("Unexpected rheometer header")
                    block += 1
                a = text.split("\t")
                if len(a) != 7 or a[0] or not a[1].isdigit():
                    continue
                temp, viscosity, rate = float(a[2]), float(a[3]), float(a[5])
                if (
                    viscosity <= 0
                    or rate <= 0
                    or not all(math.isfinite(v) for v in [temp, viscosity, rate])
                ):
                    rejected.append(
                        {
                            "file": f,
                            "line": line,
                            "reason": "nonpositive_or_nonfinite_instrument_reading",
                            "raw": a,
                        }
                    )
                    continue
                rows.append(
                    dict(
                        sample_id=f"resin-r{replicate}-b{block}-p{a[1]}",
                        group=f"replicate-{replicate}",
                        temperature=temp + 273.15,
                        shear_rate=rate,
                        target=viscosity / 1000,
                        partition=part,
                        source_file=f,
                        source_line=line,
                        source_channel="Viscosity [cP]",
                        quality=a[4]
                        + "; positive reading, no quantitative torque uncertainty available",
                    )
                )
    package(
        "057",
        "Resin flow across temperature and shear",
        "Five rheometer test runs on neat resin span temperature and shear rate. Compare a temperature-activated viscosity with a shear-thinning constitutive system. Complete instrument runs are held out, and nonpositive instrument readings are retained in the private exclusion ledger.",
        ["temperature", "shear_rate"],
        {"temperature": "K", "shear_rate": "s^-1", "target": "Pa*s"},
        {
            "temperature": "Measured plate temperature converted from degrees Celsius to Kelvin",
            "shear_rate": "Instrument-reported applied shear rate",
            "target": "Instrument-derived dynamic viscosity, converted from centipoise to Pascal seconds",
        },
        rows,
        rejected,
        [{"path": str(path.relative_to(r)), "sha256": file_sha(path)}],
        resin_templates(),
        [
            "Neat-resin subset of the source collection; no claim about all syntactic-foam formulations",
            "Replicate test runs, not independently synthesized batches",
            f"{len(rejected)} nonpositive native readings are excluded by a predeclared physical-validity rule; noisy positive readings remain",
            "No source torque-resolution uncertainty model; high-temperature low-viscosity measurements may be unreliable",
            "Retrospective engineering evidence; external scientific review remains unassessed",
        ],
        "Whole native test runs: unsuffixed and runs 1/2 train, run 3 development, run 4 test. All temperature/shear sweeps in a run remain together.",
        [
            "UTF-16 tab-delimited native instrument blocks",
            "Celsius to Kelvin; cP / 1000 to Pa*s",
            "Exclude nonpositive/nonfinite viscosity or shear rate; preserve all other noise",
            "No fitted preprocessing",
        ],
    )

    # P100-058: long-form paired responses share one graph and one parameter vector.
    r = raw / registry["P100-058"]["local_folder"]
    path = r / "raw/PDLLA15k_DSC_GPC_rheo.zip"
    rows, rejected = [], []
    with zipfile.ZipFile(path) as archive:
        for f in sorted(archive.namelist()):
            match = re.search(r"/rheology/DFS_gap0\.879_T(\d+)_smax[\d.]+$", f)
            if not match:
                continue
            temperature = int(match[1])
            part = (
                "dev" if temperature in [45, 65] else "test" if temperature in [55, 75] else "train"
            )
            lines = archive.read(f).decode("latin1").replace("\x00", "").splitlines()
            if lines[0].split("\t")[:3] != ["w", "G'", 'G"'] or lines[1].split("\t")[:3] != [
                "rad/s",
                "Pa",
                "Pa",
            ]:
                raise ValueError("Unexpected oscillatory-shear source schema")
            for line, text in enumerate(lines[2:], 3):
                if not text.strip():
                    continue
                a = [float(v) for v in text.split()]
                if len(a) != 8 or not all(math.isfinite(v) and v > 0 for v in a[:3]):
                    rejected.append(
                        {
                            "file": f,
                            "line": line,
                            "reason": "invalid_frequency_or_modulus",
                            "raw": a,
                        }
                    )
                    continue
                for channel in [0, 1]:
                    rows.append(
                        dict(
                            sample_id=f"pdlla-T{temperature}-l{line}-c{channel}",
                            group=f"temperature-{temperature}",
                            omega=a[0],
                            temperature=temperature + 273.15,
                            response_kind=channel,
                            target=a[channel + 1],
                            partition=part,
                            source_file=f,
                            source_line=line,
                            source_channel="storage" if channel == 0 else "loss",
                            quality="Native modulus; source has no compliance correction",
                        )
                    )
    package(
        "058",
        "Polymer relaxation: coupled storage and loss",
        "Oscillatory shear measurements of poly(D,L-lactide) probe elastic storage and viscous loss across frequency and temperature. A single system must explain both response channels with the same relaxation times, elastic strengths and thermal shift. Entire temperature sweeps are held out.",
        ["omega", "temperature", "response_kind"],
        {"omega": "rad/s", "temperature": "K", "response_kind": "1", "target": "Pa"},
        {
            "omega": "Applied angular oscillation frequency, in radians per second",
            "temperature": "Sweep set-point temperature encoded in the native filename; converted to Kelvin",
            "response_kind": "Requested response channel: 0 = storage modulus G prime; 1 = loss modulus G double prime. This selects an output; it contains no measured response value.",
            "target": "Instrument-reported storage or loss modulus for the selected channel",
        },
        rows,
        rejected,
        [{"path": str(path.relative_to(r)), "sha256": file_sha(path)}],
        relaxation_templates(),
        [
            "One polymer batch; temperature sweeps are condition blocks, not independent specimens",
            "Source rheology was not compliance-corrected",
            "Both response channels are fitted jointly; this is not a held-out cross-response confirmation",
            "No target-derived tan-delta, complex viscosity or other measured modulus is a permitted input",
            "Retrospective temperature interpolation, not proof of molecular mechanism or new constitutive laws",
        ],
        "Train temperatures 40/50/60/70/80 C; development 45/65 C; test 55/75 C. Each temperature's full frequency sweep and both response channels stay together.",
        [
            "Native plain-text rheometer output; exclude duplicate proprietary files",
            "Long-form paired responses with one channel selector; no derived response features",
            "Filename Celsius set point to Kelvin; all other selected source units retained",
            "No fitted preprocessing",
        ],
    )
    shutil.copyfile(Path(__file__), output / "prepare.py")
    write_json(
        output / "EDITION.json",
        {
            "edition_id": "equation-pack-v1",
            "version": "1.0.0rc5",
            "status": "local_acceptance_preview",
            "scenarios": [x["scenario_id"] for x in receipts],
            "historical_edition_modified": False,
            "source": "Registry-aligned local native files; no new downloads",
            "public_release_authorized": False,
        },
        immutable=True,
    )
    write_json(output / "ADMISSION_AUDIT.json", receipts, immutable=True)
    (output / "README.md").write_text(
        "# Connected-equation scenarios\n\nThree compact, source-aligned local research scenarios for thermal radiation, viscous flow and coupled viscoelastic response. Use with Principia-ASD rc5. These extend the local library; the frozen forty-scenario edition remains unchanged.\n\nEach scenario documents native units, group splits, exclusions, source hashes and scientific limits. The equation templates are disclosed physical priors, never novelty claims. Private targets remain in a separate evaluator directory. Run `python prepare.py --help` for exact reconstruction; install the matching package first.\n"
    )
    return receipts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    args = parser.parse_args()
    for receipt in prepare(args.raw, args.output, args.vault):
        print(receipt["scenario_id"], receipt["rows"], "excluded", receipt["excluded"])
