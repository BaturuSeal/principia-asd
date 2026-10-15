"""Dedicated entry point for the frozen laboratory development worker."""


def execute_worker(folder):
    from .adapter_worker import execute_worker as execute

    return execute(folder, adapter="laboratory", entrypoint=__file__)
