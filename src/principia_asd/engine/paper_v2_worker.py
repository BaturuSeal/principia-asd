"""Dedicated entry point for the frozen Paper v2 development worker."""


def execute_worker(folder):
    from .adapter_worker import execute_worker as execute

    return execute(folder, adapter="paper_v2", entrypoint=__file__)
