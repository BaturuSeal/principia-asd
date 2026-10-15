"""Disposable browser fixture: real controller/checkpoints/fits, scripted replies.

Never uses provider credentials, network models, private targets or leaderboard
exports. Every run first stops after initialization, so the browser can exercise
safe checkpoint resume. Use only on a separate port and fresh private workspace.
"""

import argparse
import sys
import tempfile
from pathlib import Path


def main():
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8152)
    args = parser.parse_args()
    if args.port == 8150:
        parser.error("Use a separate fixture port")
    import numpy as np

    import principia_asd.bound_jobs as jobs
    import principia_asd.web.server as web
    from principia_asd.engine.bound_checkpoint import DurableBoundRun
    from principia_asd.engine.bound_engine import BoundEngine
    from principia_asd.engine.bound_engine_v2 import SchemaBoundEngine
    from principia_asd.io import read_csv, read_json, write_csv, write_json
    from principia_asd.methods.registry import DEFAULT_ROLES
    from principia_asd.runtime import log_event

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verify_bound_engine import ScriptedGateway

    args.workspace.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="bound-ui-fixture-", dir=args.workspace))
    scenario = root / "data/scenarios/SYNTHETIC"
    task = {
        "task_id": "SYNTHETIC.fixture",
        "scenario_id": "SYNTHETIC",
        "title": "Synthetic UI fixture — scripted, no live models",
        "inputs": ["x"],
        "input_units": {"x": "dimensionless"},
        "output": "y",
        "output_units": "dimensionless",
        "metric": {"primary": "rmse"},
        "stability": {"ranking": False},
        "split": {"train": "train.csv", "dev": "dev.csv"},
        "test_exposure": "engineering fixture; no test set",
    }
    write_json(scenario / "task-contracts/task-001.json", task)
    write_json(
        scenario / "scenario.json",
        {
            "title": task["title"],
            "domain": "Engineering fixture",
            "description": "Scripted model responses and real numerical fitting. Not scientific evidence.",
            "rows": {"train": 7, "dev": 3, "test": 0},
            "limitations": ["No live models, provider credentials, test targets or ranking."],
        },
    )
    for label, xs in [("train", range(-3, 4)), ("dev", [-2.5, -0.5, 1.5])]:
        rows = [
            {
                "sample_id": f"{label}{i}",
                "group": label,
                "x": float(x),
                "y": float(0.4 + 0.2 * np.tanh(x / 2)),
            }
            for i, x in enumerate(xs)
        ]
        write_csv(scenario / f"{label}.csv", rows, ["sample_id", "group", "x", "y"])
    settings = {
        "workspace": str(root / "private"),
        "data_root": str(root / "data"),
        "leaderboard_root": str(root / "boards"),
        "vault": str(root / "unused-vault"),
    }
    write_json(root / "settings.json", settings)
    write_json(
        root / "private/capabilities.json",
        {
            m: {"state": "verified", "scope": "scripted fixture only"}
            for m in DEFAULT_ROLES.values()
        },
    )

    class SimulatedInterruption(BaseException):
        pass

    def launch_fixture(folder):
        if (folder / "cancel.requested").exists():
            return
        first = not (folder / "checkpoints").exists()

        def checkpoint(record):
            if first and record["type"] == "commit":
                raise SimulatedInterruption()

        gateway = ScriptedGateway()
        protocol = read_json(folder / "request.json")["scope"].removeprefix(
            "engineering_only_explicit_state_"
        )
        engine_class = {"v1": BoundEngine, "v2": SchemaBoundEngine}[protocol]
        engine = engine_class(
            task,
            read_csv(scenario / "train.csv"),
            read_csv(scenario / "dev.csv"),
            gateway=gateway,
            run_id=folder.name,
            stopped=lambda: (folder / "cancel.requested").exists(),
            event=lambda stage, detail: log_event(folder, stage, detail),
        )
        runner = DurableBoundRun(
            engine,
            folder,
            provider_binding={"scope": "scripted-zero-api-ui-fixture"},
            after_record=checkpoint,
        )
        try:
            result = runner.run()
        except SimulatedInterruption:
            write_json(
                folder / "state.json",
                {
                    "status": "interrupted",
                    "reason": "Scripted fixture stopped after a committed initialization; no request was sent.",
                },
            )
            return
        write_json(folder / "state.json", {"status": result["status"]})
        write_json(
            folder / "fixture-verification.json",
            {
                "scope": "scripted-browser-engineering-fixture",
                "protocol_revision": protocol,
                "real_api_calls": 0,
                "scripted_requests": len(gateway.calls),
                "fitting_attempts": result["host_submission"]["accounting"]["fitting_attempts"],
                "nomination_slots": len(result["selection"]["nominations"]),
                "conformance": result["conformance"],
                "result_sha256": result["sha256"],
            },
        )

    class FixtureApp(web.App):
        def start(self, request):
            if request.get("method_id") != jobs.METHOD_ID:
                raise ValueError(
                    "This isolated browser fixture permits only the development Engine"
                )
            return super().start(request)

        def get_run(self, *a, **kw):
            return super().get_run(*a, **kw) | {"fixture": True}

    jobs.launch = launch_fixture
    web.App = FixtureApp
    print(f"FIXTURE_ROOT={root}", flush=True)
    web.serve(settings, args.port)


if __name__ == "__main__":
    main()
