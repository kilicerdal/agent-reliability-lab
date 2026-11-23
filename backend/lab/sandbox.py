"""Fault injection and real workload. This module is never exposed as an agent tool."""

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

from .db import connect

SCENARIOS = {
    "database-slowdown": {
        "title": "Order lookup slowed down",
        "alert": "Order lookup latency exceeded 100 ms.",
        "cause": "db_latency",
        "delay": 0.18,
        "worker": True,
        "inventory": "healthy",
        "required": ["query_slow", "query_config_changed"],
    },
    "worker-failure": {
        "title": "Accepted orders are not completing",
        "alert": "Accepted orders remain queued while the API responds.",
        "cause": "worker_stopped",
        "delay": 0,
        "worker": False,
        "inventory": "healthy",
        "required": ["worker_offline", "worker_config_changed"],
    },
    "dependency-failure": {
        "title": "Processing fails after a deployment",
        "alert": "Order processing started failing following a deployment.",
        "cause": "dependency_config",
        "delay": 0,
        "worker": True,
        "inventory": "wrong-region",
        "required": ["inventory_failed", "inventory_config_changed"],
    },
    "healthy": {
        "title": "Healthy control",
        "alert": "Verify whether this order workflow is healthy.",
        "cause": "healthy",
        "delay": 0,
        "worker": True,
        "inventory": "healthy",
        "required": ["order_completed", "query_ok"],
    },
}


def record(c, e, service, signal, detail):
    c.execute(
        "INSERT INTO observations(experiment,service,signal,detail) VALUES(%s,%s,%s,%s)",
        (e, service, signal, detail),
    )


def inject(kind):
    s = SCENARIOS[kind]
    e = str(uuid.uuid4())
    with connect() as c:
        c.execute(
            "INSERT INTO experiments(id,kind,worker_enabled,inventory_mode,query_delay) VALUES(%s,%s,%s,%s,%s)",
            (e, kind, s["worker"], s["inventory"], s["delay"]),
        )
        record(
            c,
            e,
            "deployment",
            "deployment_applied",
            "Synthetic release 1.1 applied; review individual settings before assigning cause.",
        )
        for svc, sig, detail in [
            (
                "database",
                "query_config_changed",
                f"Query delay setting changed to {s['delay']} seconds",
            ),
            (
                "worker",
                "worker_config_changed",
                f"Worker enabled setting is {s['worker']}",
            ),
            (
                "inventory",
                "inventory_config_changed",
                f"Inventory region setting is {s['inventory']}",
            ),
        ]:
            record(c, e, svc, sig, detail)
        c.execute("INSERT INTO orders(experiment) VALUES(%s)", (e,))
    return e


def lookup(e):
    start = time.monotonic()
    with connect() as c:
        cfg = c.execute(
            "SELECT query_delay FROM experiments WHERE id=%s", (e,)
        ).fetchone()
        if not cfg:
            raise KeyError(e)
        c.execute("SELECT pg_sleep(%s)", (cfg["query_delay"],))
        rows = c.execute(
            "SELECT id,status FROM orders WHERE experiment=%s", (e,)
        ).fetchall()
        ms = round((time.monotonic() - start) * 1000, 2)
        record(
            c,
            e,
            "database",
            "query_slow" if ms >= 100 else "query_ok",
            f"Actual PostgreSQL order lookup: {ms} ms; {len(rows)} rows",
        )
    return rows


def tick(e):
    with connect() as c:
        cfg = c.execute("SELECT * FROM experiments WHERE id=%s", (e,)).fetchone()
        if not cfg:
            raise KeyError(e)
        rows = c.execute(
            "SELECT id FROM orders WHERE experiment=%s AND status='queued' FOR UPDATE",
            (e,),
        ).fetchall()
        if not cfg["worker_enabled"]:
            record(
                c,
                e,
                "worker",
                "worker_offline",
                f"Worker not running; {len(rows)} queued orders",
            )
            return
        if not rows:
            return
        record(
            c,
            e,
            "worker",
            "worker_heartbeat",
            "Background worker polling queued orders",
        )
        response = httpx.get(
            os.environ.get("LAB_INVENTORY_URL", "http://127.0.0.1:8811") + "/stock",
            params={"region": cfg["inventory_mode"]},
            timeout=3,
        )
        if response.status_code != 200:
            record(
                c,
                e,
                "inventory",
                "inventory_failed",
                f"Inventory returned HTTP {response.status_code} for region {cfg['inventory_mode']}; order remains queued",
            )
        else:
            c.execute(
                "UPDATE orders SET status='completed' WHERE experiment=%s AND status='queued'",
                (e,),
            )
            record(
                c,
                e,
                "worker",
                "order_completed",
                f"{len(rows)} orders completed after successful inventory response",
            )


def reproduce(kind):
    e = inject(kind)
    # The same worker implementation can run continuously or once for a bounded capture.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(tick, e).result(timeout=10)
    lookup(e)
    return e


def fingerprint(e):
    import hashlib
    import json

    with connect() as c:
        cfg = c.execute(
            "SELECT id,worker_enabled,inventory_mode,query_delay FROM experiments WHERE id=%s",
            (e,),
        ).fetchone()
        rows = c.execute(
            "SELECT id,status FROM orders WHERE experiment=%s ORDER BY id", (e,)
        ).fetchall()
        logs = c.execute(
            "SELECT id,service,signal,detail FROM observations WHERE experiment=%s ORDER BY id",
            (e,),
        ).fetchall()
    return hashlib.sha256(
        json.dumps([cfg, rows, logs], sort_keys=True).encode()
    ).hexdigest()
