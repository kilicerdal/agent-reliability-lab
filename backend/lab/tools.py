"""Agent boundary: allowlisted read-only operations, always scoped to one experiment."""

from .db import connect

NAMES = ["read_logs", "read_deployments", "read_queue", "read_health"]
TOOLS = [
    {
        "type": "function",
        "name": n,
        "description": d,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    }
    for n, d in zip(
        NAMES,
        [
            "Inspect recent workload observations with stable evidence IDs.",
            "Inspect recent deployment and configuration change records.",
            "Inspect order statuses and queue depth for this investigation.",
            "Inspect last recorded service signals, not a new live probe.",
        ],
    )
]


def dispatch(name, args, e):
    if name not in NAMES or args != {}:
        raise ValueError("Tool or arguments not permitted")
    with connect(readonly=True) as c:
        if name == "read_queue":
            rows = c.execute(
                "SELECT id,status FROM orders WHERE experiment=%s ORDER BY id LIMIT 30",
                (e,),
            ).fetchall()
            return {
                "orders": rows,
                "queued": sum(r["status"] == "queued" for r in rows),
            }
        rows = c.execute(
            "SELECT id,service,signal,detail FROM observations WHERE experiment=%s ORDER BY id LIMIT 40",
            (e,),
        ).fetchall()
    if name == "read_deployments":
        rows = [
            r
            for r in rows
            if "config_changed" in r["signal"] or r["signal"] == "deployment_applied"
        ]
    elif name == "read_health":
        rows = [
            r
            for r in rows
            if "config_changed" not in r["signal"]
            and r["signal"] != "deployment_applied"
        ]
    return {
        "records": [
            {
                "evidence_id": f"obs-{r['id']}",
                **{k: v for k, v in r.items() if k != "id"},
            }
            for r in rows
        ]
    }
