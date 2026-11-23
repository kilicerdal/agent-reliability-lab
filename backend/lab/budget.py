"""Atomic reservation across processes. Unknown billed usage keeps its full reservation."""

import os
import sqlite3
import time
import uuid
from pathlib import Path

CAP = 55.0
RESERVE = 0.25


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, path=None):
        self.path = Path(
            path or os.environ.get("LAB_BUDGET_FILE", ".private/budget.sqlite")
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS charges(id TEXT PRIMARY KEY, amount REAL NOT NULL, state TEXT NOT NULL, at REAL NOT NULL)"
            )

    def db(self):
        return sqlite3.connect(self.path, timeout=15)

    def reserve(self):
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            used = c.execute("SELECT COALESCE(sum(amount),0) FROM charges").fetchone()[
                0
            ]
            if used + RESERVE > CAP:
                raise BudgetExceeded("Project API allowance exhausted; no request sent")
            rid = str(uuid.uuid4())
            c.execute(
                "INSERT INTO charges VALUES(?,?,?,?)",
                (rid, RESERVE, "reserved", time.time()),
            )
        return rid

    def settle(self, rid, input_tokens, output_tokens):
        # Standard, uncached upper estimate. Cached inputs may make the actual invoice lower.
        amount = (input_tokens * 2 + output_tokens * 10) / 1_000_000
        if amount > RESERVE:
            raise BudgetExceeded(
                "Usage exceeded request reservation: stop and review pricing"
            )
        with self.db() as c:
            c.execute(
                "UPDATE charges SET amount=?,state='usage-estimate' WHERE id=?",
                (amount, rid),
            )
        return amount

    def summary(self):
        with self.db() as c:
            rows = c.execute(
                "SELECT state,sum(amount),count(*) FROM charges GROUP BY state"
            ).fetchall()
        return {
            "ceiling_usd": CAP,
            "accounted_usd": round(sum(r[1] for r in rows), 6),
            "requests": sum(r[2] for r in rows),
            "unsettled_requests": sum(r[2] for r in rows if r[0] == "reserved"),
            "scope": "Local project ledger only; not account-wide billing. Do not delete or reset it. Amounts are conservative standard-price token estimates.",
        }
