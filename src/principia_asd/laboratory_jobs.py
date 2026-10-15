"""Frozen development jobs for the explicit-state Agent Laboratory adaptation."""

from . import adapter_jobs
from .adapter_jobs import verify_finished as verify_finished
from .control_jobs import environment

SCOPE = "engineering_only_laboratory_explicit_v1"
METHOD_ID = "agent_laboratory_explicit"


def prepare(settings, scenario, **kwargs):
    return adapter_jobs.prepare(
        settings, scenario, adapter="laboratory", environment_probe=environment, **kwargs
    )


def verify_binding(folder, *, check_environment=False):
    return adapter_jobs.verify_binding(
        folder,
        adapter="laboratory",
        check_environment=check_environment,
        environment_probe=environment,
    )


def main():
    adapter_jobs.main("laboratory")


if __name__ == "__main__":
    main()
