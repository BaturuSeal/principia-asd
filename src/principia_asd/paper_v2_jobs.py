"""Frozen development jobs for the explicit-state data-to-paper v2 adaptation."""

from . import adapter_jobs
from .adapter_jobs import verify_finished as verify_finished
from .control_jobs import environment

SCOPE = "engineering_only_data_to_paper_explicit_v2"
METHOD_ID = "data_to_paper_explicit"


def prepare(settings, scenario, **kwargs):
    return adapter_jobs.prepare(
        settings, scenario, adapter="paper_v2", environment_probe=environment, **kwargs
    )


def verify_binding(folder, *, check_environment=False):
    return adapter_jobs.verify_binding(
        folder,
        adapter="paper_v2",
        check_environment=check_environment,
        environment_probe=environment,
    )


def main():
    adapter_jobs.main("paper_v2")


if __name__ == "__main__":
    main()
