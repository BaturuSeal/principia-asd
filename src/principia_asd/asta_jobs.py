"""Frozen development jobs for Asta on explicit host state.

This entry point does not enable UI selection or private-test evaluation.
"""

from . import adapter_jobs
from .adapter_jobs import verify_finished as verify_finished
from .control_jobs import environment

SCOPE = "engineering_only_asta_explicit_v1"
METHOD_ID = "asta_autodiscovery_explicit"
HANDOFF_ROLES = {
    f"hypothesis-{node}:{stage}": role
    for node in range(1, 5)
    for stage, role in {
        "nomination": "planner",
        "prior:1": "critic",
        "prior:2": "critic",
        "engineering": "coder",
        "posterior:1": "critic",
        "posterior:2": "critic",
    }.items()
} | {"report": "reporter"}


def prepare(settings, scenario, **kwargs):
    return adapter_jobs.prepare(
        settings, scenario, adapter="asta", environment_probe=environment, **kwargs
    )


def verify_binding(folder, *, check_environment=False):
    return adapter_jobs.verify_binding(
        folder,
        adapter="asta",
        check_environment=check_environment,
        environment_probe=environment,
    )


def main():
    adapter_jobs.main("asta")


if __name__ == "__main__":
    main()
