"""Dedicated entry point for the frozen Asta development worker."""


def execute_worker(folder):
    from .adapter_worker import execute_worker as execute

    return execute(folder, adapter="asta", entrypoint=__file__)
