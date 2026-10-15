"""Dedicated entry point for the frozen paper development worker."""


def execute_worker(folder):
    from .adapter_worker import execute_worker as execute

    return execute(folder, adapter="paper", entrypoint=__file__)
