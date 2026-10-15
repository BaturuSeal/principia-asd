"""Run with a freshly installed wheel's Python, without the repository on PYTHONPATH."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import principia_asd
from principia_asd.engine.search import execute_method


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--leaderboard-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    assert "site-packages" in principia_asd.__file__
    package = Path(principia_asd.__file__).parent
    assert all((package / "web" / name).is_file() for name in ["index.html", "app.js", "style.css"])
    for command in [
        "serve",
        "companion",
        "build-site",
        "catalog",
        "audit",
        "prepare",
        "validate",
        "run",
        "resume",
        "evaluate",
        "review",
        "leaderboard",
        "export",
        "replay",
    ]:
        subprocess.run(
            [sys.executable, "-I", "-m", "principia_asd.cli", command, "--help"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    task = {
        "inputs": ["x"],
        "output": "target",
        "metric": {"primary": "mae"},
        "stability": {"domain": "finite"},
        "task_id": "fixture",
    }
    train = [{"x": i, "target": 2 * i + 1, "group": str(i)} for i in range(20)]
    dev = [{"x": i, "target": 2 * i + 1, "group": str(i)} for i in range(21, 30)]
    assert execute_method("linear_control", task, train, dev)["rules"][0]["dev_error"] < 1e-10
    with tempfile.TemporaryDirectory(prefix="principia-install-smoke-") as tmp:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"PYTHONPATH", "SILICONFLOW_API_KEY"}
            and not any(s in k for s in ["TOKEN", "SECRET"])
        }
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        command = [
            sys.executable,
            "-I",
            "-m",
            "principia_asd.cli",
            "serve",
            "--port",
            "8151",
            "--workspace",
            tmp,
            "--data-root",
            str(args.data_root),
            "--leaderboard-root",
            str(args.leaderboard_root),
            "--vault",
            str(Path(tmp) / "no-private-targets"),
        ]
        with (Path(tmp) / "server.log").open("w") as log:
            process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
            try:
                response = None
                for _ in range(60):
                    if process.poll() is not None:
                        raise RuntimeError((Path(tmp) / "server.log").read_text())
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:8151/api/config", timeout=1
                        ) as r:
                            response = json.load(r)
                        break
                    except OSError:
                        time.sleep(0.1)
                assert (
                    response
                    and response["version"] == principia_asd.__version__
                    and not response["api_configured"]
                )
                for url in [
                    "http://127.0.0.1:8151/",
                    "http://127.0.0.1:8151/app.js",
                    "http://127.0.0.1:8151/style.css",
                ]:
                    with urllib.request.urlopen(url) as r:
                        assert r.status == 200 and len(r.read()) > 100
                checks = [
                    urllib.request.Request(
                        "http://127.0.0.1:8151/api/config",
                        headers={"Origin": "https://untrusted.example"},
                    ),
                    urllib.request.Request(
                        "http://127.0.0.1:8151/api/config", headers={"Host": "untrusted.example"}
                    ),
                    urllib.request.Request(
                        "http://127.0.0.1:8151/api/runs",
                        data=b"{}",
                        headers={"Content-Type": "application/json"},
                    ),
                ]
                for request in checks:
                    try:
                        urllib.request.urlopen(request)
                    except urllib.error.HTTPError as e:
                        assert e.code in {400, 403}
                    else:
                        raise AssertionError("Origin/host/CSRF protection did not reject request")
            finally:
                process.terminate()
                process.wait(timeout=10)
    result = {
        "version": principia_asd.__version__,
        "status": "passed",
        "source_is_installed_distribution": True,
        "cli_help_commands": 14,
        "numerical_fixture": "passed",
        "packaged_ui_assets": "passed",
        "localhost_server": "passed",
        "host_origin_csrf_denials": "passed",
        "api_calls": 0,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
