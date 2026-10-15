"""Probe exact generation profiles once; retain unknown usage without retry."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from principia_asd.engine.search import decode_json
from principia_asd.io import write_json
from principia_asd.llm.siliconflow import PRICE_SOURCE, PROFILES, SiliconFlowClient
from principia_asd.store.ledger import CostLedger

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--env-file", type=Path, required=True)
    p.add_argument(
        "--carry-forward-cny",
        type=float,
        default=0,
        help="Conservative reservations from an explicitly retained earlier preview",
    )
    a = p.parse_args()
    ledger = CostLedger(a.workspace / "costs.sqlite")
    if a.carry_forward_cny > 0 and ledger.get("prior-preview-reservations") is None:
        ledger.reserve(
            "prior-preview-reservations",
            a.carry_forward_cny,
            {
                "source": "preserved preview-v1 ledger receipts",
                "scope": "one conservative carry-forward; old paid calls never replayed",
            },
        )
        ledger.record(
            {"request_id": "prior-preview-reservations", "state": "unknown", "actual_cny": None}
        )

    def probe(model):
        client = SiliconFlowClient(
            env_file=a.env_file,
            ledger=ledger,
            artifact_dir=a.workspace / "probes",
            require_capabilities=False,
        )
        try:
            r = client.complete(
                model=model,
                system="Return JSON only.",
                prompt='Reply with {"ok": true, "task": "scientific rule discovery capability probe"}.',
                max_tokens=128,
                request_id="capability-v2--" + model,
            )
            if decode_json(r["text"]).get("ok") is not True:
                raise ValueError("JSON capability not confirmed")
            return model, {
                "state": "verified",
                "model": model,
                "generation": PROFILES[model],
                "usage": r["usage"],
                "json": True,
                "text": True,
                "vision": "not_probed",
                "tools": "host structured JSON actions only",
                "price_source": PRICE_SOURCE,
            }
        except Exception as e:
            return model, {"state": "unavailable", "model": model, "reason": str(e)[:250]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        result = dict(pool.map(probe, PROFILES))
    write_json(a.workspace / "capabilities.json", result)
    write_json(a.workspace / "price-snapshot.json", {"source": PRICE_SOURCE, "models": PROFILES})
    print(result)
    print(ledger.summary())
