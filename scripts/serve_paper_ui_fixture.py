"""Installed worker/browser fixture with synthetic transport and no real API calls."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--protocol", choices=["v1", "v2"], default="v1")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--port", type=int, default=8153)
    args = parser.parse_args()
    if args.port == 8150:
        parser.error("Use a separate fixture port")
    import principia_asd.web.server as web
    from principia_asd import bound_jobs

    if args.protocol == "v2":
        from principia_asd import paper_v2_jobs as paper_jobs
    else:
        from principia_asd import paper_jobs
    from principia_asd.io import read_json, write_json
    from principia_asd.store.ledger import CostLedger

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verify_paper_worker import helper

    args.workspace.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="paper-ui-fixture-", dir=args.workspace))
    settings, scenario = helper().fixture(root)
    task_path = scenario / "task-contracts/task-001.json"
    task = read_json(task_path) | {
        "task_id": "SYNTHETIC.fixture",
        "title": "Synthetic data-to-paper fixture",
        "input_units": {"x": "dimensionless"},
        "output_units": "dimensionless",
    }
    write_json(task_path, task)
    write_json(
        scenario / "scenario.json",
        {
            "title": task["title"],
            "domain": "Engineering fixture",
            "description": "Scripted reports and real numerical computations; not scientific evidence.",
            "rows": {"train": 7, "dev": 3, "test": 0},
            "limitations": ["Synthetic transport; no real API, test targets or public ranking."],
        },
    )
    runs = {}
    for case in ("complete", "incorrect_report"):
        folder = paper_jobs.prepare(settings, scenario)
        config = read_json(folder / "launch.json")
        result = subprocess.run(
            [
                config["interpreter"],
                "-I",
                "-B",
                str(Path(__file__).with_name("verify_paper_worker.py").resolve()),
                "--child",
                str(folder),
                "--case",
                case,
            ],
            capture_output=True,
            timeout=60,
        )
        (folder / "fixture.log").write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr.decode()[-1800:]
        runs[case] = folder.name
    write_json(root / "fixture.json", {"root": str(root), "runs": runs, "real_api_calls": 0})

    def launch_fixture(folder):
        if (folder / "cancel.requested").exists():
            return
        config = read_json(folder / "launch.json")
        first = not (folder / "mock-dispatches.jsonl").exists()
        next_stop = CostLedger(Path(settings["workspace"]) / "costs.sqlite").summary()["requests"] + 2
        result = subprocess.run(
            [
                config["interpreter"],
                "-I",
                "-B",
                str(Path(__file__).with_name("verify_paper_worker.py").resolve()),
                "--child",
                str(folder),
                "--case",
                "complete",
                "--crash-at",
                str(next_stop) if first else "-1",
            ],
            capture_output=True,
            timeout=60,
        )
        with (folder / "fixture.log").open("ab") as log:
            log.write(result.stdout + result.stderr)
        assert result.returncode == (91 if first else 0), result.stderr.decode()[-1800:]

    class FixtureApp(web.App):
        def start(self, request):
            if not args.interactive:
                raise ValueError("Read-only synthetic fixture; live runs are disabled")
            if args.protocol != "v2" or request.get("method_id") != paper_jobs.METHOD_ID:
                raise ValueError("Only scripted Paper v2 development is available in this fixture")
            return super().start(request)

        def get_run(self, *a, **kw):
            return super().get_run(*a, **kw) | {"fixture": True}

    if args.interactive:
        bound_jobs.launch = launch_fixture
    web.App = FixtureApp
    print(json.dumps({"root": str(root), "runs": runs}), flush=True)
    web.serve(settings, args.port)


if __name__ == "__main__":
    main()
