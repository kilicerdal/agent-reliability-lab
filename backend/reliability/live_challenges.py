"""Build reproducible recovery challenges against the isolated order application."""

import os

import httpx
from psycopg.errors import QueryCanceled

from backend.lab.db import connect
from backend.lab.sandbox import record, reproduce
from backend.lab.tools import NAMES, dispatch

from .assurance import EvidenceJudgment

SCENARIOS = {
    "http-timeout": (
        "database-slowdown",
        "db_latency",
        "query_slow",
        "query_config_changed",
        "Order lookups are slow. Use the workload records and configuration to establish the cause.",
    ),
    "sql-timeout": (
        "dependency-failure",
        "dependency_config",
        "inventory_failed",
        "inventory_config_changed",
        "Orders remain queued. Inspect current workload and deployment evidence.",
    ),
    "telemetry-loss": (
        "worker-failure",
        "unknown",
        "telemetry_gap",
        "configuration_gap",
        "An order delay was reported during an ingestion outage. Assess whether the surviving evidence identifies a cause.",
    ),
    "stale-conflict": (
        "worker-failure",
        "worker_stopped",
        "worker_offline",
        "worker_config_changed",
        "A cached summary attributes the backlog to the database. Investigate the current incident.",
    ),
}


class LiveChallenge:
    def __init__(self, scenario):
        kind, self.cause, mechanism, configuration, self.alert = SCENARIOS[scenario]
        self.name = scenario
        self.experiment = reproduce(kind)
        with connect() as conn:
            if scenario == "telemetry-loss":
                conn.execute(
                    "DELETE FROM observations WHERE experiment=%s", (self.experiment,)
                )
                record(
                    conn,
                    self.experiment,
                    "telemetry",
                    "telemetry_gap",
                    "The collector lost all workload samples during the affected interval.",
                )
                record(
                    conn,
                    self.experiment,
                    "deployment",
                    "configuration_gap",
                    "The deployment record survived without effective service settings.",
                )
            if scenario == "stale-conflict":
                record(
                    conn,
                    self.experiment,
                    "database",
                    "stale_summary",
                    "Historical only: a previous deployment reported a slow SQL lookup.",
                )
            observations = conn.execute(
                "SELECT id, signal FROM observations WHERE experiment=%s",
                (self.experiment,),
            ).fetchall()
        self.rubric = [
            EvidenceJudgment(
                kind=kind,
                evidence_id=f"obs-{row['id']}",
                verdict=(
                    "supports"
                    if row["signal"] == required
                    else "contradicts"
                    if row["signal"] == "stale_summary" and kind == "mechanism"
                    else "irrelevant"
                ),
            )
            for row in observations
            for kind, required in (
                ("mechanism", mechanism),
                ("configuration", configuration),
            )
        ]

    def tools(self):
        exposed = []

        def read(name, args):
            if name not in NAMES or args != {}:
                raise ValueError("Tool or arguments denied")
            if name == "read_logs" and not exposed:
                if self.name == "http-timeout":
                    endpoint = (
                        os.environ.get("LAB_INVENTORY_URL", "http://127.0.0.1:8811")
                        + "/stock"
                    )
                    try:
                        httpx.get(endpoint, params={"delay_ms": 180}, timeout=0.06)
                    except httpx.ReadTimeout:
                        exposed.append("http_read_timeout")
                        return {"error": "timeout", "retryable": True}
                    raise RuntimeError("The synthetic HTTP timeout did not fire")
                if self.name == "sql-timeout":
                    try:
                        with connect(readonly=True) as conn:
                            conn.execute("SET LOCAL statement_timeout = '20ms'")
                            conn.execute("SELECT pg_sleep(0.08)")
                    except QueryCanceled:
                        exposed.append("postgres_statement_timeout")
                        return {"error": "timeout", "retryable": True}
                    raise RuntimeError("The synthetic PostgreSQL timeout did not fire")
            return dispatch(name, args, self.experiment)

        return read, exposed
