"""Transactional campaign-wide reservation ledger; retries never replay paid requests."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path


class DuplicateRequest(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class CostLedger:
    def __init__(self, path: Path, cap_cny: float = 3000):
        self.path = Path(path)
        self.cap_cny = float(cap_cny)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY,state TEXT,reserved_cny REAL,actual_cny REAL,payload TEXT)"
            )
            db.execute("CREATE TABLE IF NOT EXISTS policy(key TEXT PRIMARY KEY,value TEXT)")
            db.execute("INSERT OR IGNORE INTO policy VALUES(?,?)", ("cap_cny", str(self.cap_cny)))
            stored = float(
                db.execute("SELECT value FROM policy WHERE key=?", ("cap_cny",)).fetchone()[0]
            )
            if stored != self.cap_cny:
                raise ValueError("Ledger cap is immutable")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def reserve(
        self, request_id, amount_cny, payload=None, *, attempt_id=None, attempt_cap_cny=None
    ):
        amount = float(amount_cny)
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Reservation must be positive and finite")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM requests WHERE request_id=?", (request_id,)).fetchone():
                raise DuplicateRequest(
                    "Request identity already dispatched or reserved; no replay: " + request_id
                )
            total = db.execute(
                "SELECT COALESCE(SUM(COALESCE(actual_cny,reserved_cny)),0) FROM requests"
            ).fetchone()[0]
            if total + amount > self.cap_cny + 1e-9:
                raise BudgetExceeded("Campaign cap would be exceeded")
            metadata = dict(payload or {})
            if attempt_id is not None:
                if (
                    attempt_cap_cny is None
                    or not math.isfinite(attempt_cap_cny)
                    or attempt_cap_cny <= 0
                ):
                    raise ValueError("Attempt cap must be positive and finite")
                spent = sum(
                    float(cost)
                    for cost, encoded in db.execute(
                        "SELECT COALESCE(actual_cny,reserved_cny),payload FROM requests"
                    )
                    if json.loads(encoded).get("attempt_id") == attempt_id
                )
                if spent + amount > attempt_cap_cny + 1e-9:
                    raise BudgetExceeded("Attempt monetary cap would be exceeded")
                metadata["attempt_id"] = attempt_id
                metadata["attempt_cap_cny"] = attempt_cap_cny
            db.execute(
                "INSERT INTO requests VALUES(?,?,?,?,?)",
                (request_id, "reserved", amount, None, json.dumps(metadata)),
            )

    def record(self, payload, reserved_cny=0):
        request_id = str(payload["request_id"])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT state,reserved_cny,payload FROM requests WHERE request_id=?", (request_id,)
            ).fetchone()
            if old is None:
                raise ValueError("Cannot settle an unreserved request")
            if old[0] != "reserved":
                raise DuplicateRequest("Terminal request receipt cannot be changed")
            actual = payload.get("actual_cny")
            if actual is not None and (not math.isfinite(actual) or actual < 0):
                raise ValueError("Invalid recorded cost")
            merged = json.loads(old[2]) | payload
            db.execute(
                "UPDATE requests SET state=?,actual_cny=?,payload=? WHERE request_id=?",
                (payload.get("state", "unknown"), actual, json.dumps(merged), request_id),
            )

    def get(self, request_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT state,reserved_cny,actual_cny,payload FROM requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
        return (
            None
            if row is None
            else dict(
                state=row[0], reserved_cny=row[1], actual_cny=row[2], payload=json.loads(row[3])
            )
        )

    def summary(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT state,COALESCE(actual_cny,reserved_cny) FROM requests"
            ).fetchall()
        total = sum(float(r[1]) for r in rows)
        return {
            "cap_cny": self.cap_cny,
            "requests": len(rows),
            "accounted_cny": total,
            "remaining_cny": max(0, self.cap_cny - total),
            "states": {s: sum(r[0] == s for r in rows) for s, _ in rows},
            "unknown_usage_reserved": sum(
                float(v) for s, v in rows if s in {"unknown", "reserved"}
            ),
        }
