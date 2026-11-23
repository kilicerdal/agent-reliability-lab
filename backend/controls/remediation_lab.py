"""Run stateful, operator-approved recovery scenarios against the synthetic workload."""

import argparse
import json
from pathlib import Path

import anyio

from backend.lab.db import connect, init_db
from backend.lab.sandbox import reproduce, tick
from backend.lab.tools import dispatch

from .approval import install
from .evidence import mcp_client, operator_cli, restart_outcome, state
from .server import REQUEST


async def run_scenario(persistent_inventory_fault):
    experiment = reproduce("worker-failure")
    initial = state(experiment)
    timeline = []

    def snapshot(event):
        timeline.append(
            {
                "event": event,
                "state": state(experiment),
                "queue_observation": dispatch("read_queue", {}, experiment),
            }
        )

    if persistent_inventory_fault:
        with connect() as conn:
            conn.execute(
                "UPDATE experiments SET inventory_mode='wrong-region' WHERE id=%s",
                (experiment,),
            )
    tick(experiment)
    snapshot("incident_observed")
    async with mcp_client(experiment) as client:
        await client.list_tools()
        response = await client.call_tool(REQUEST, {})
        if response.is_error or response.structured_content is None:
            raise RuntimeError("Could not submit the scoped restart request")
        requested = response.structured_content["status"]
    tick(experiment)
    snapshot("pending_operator_review")
    statuses = []
    for event in ("operator_approved", "operator_retried"):
        result = operator_cli(experiment, experiment)
        result.check_returncode()
        statuses.append(json.loads(result.stdout.splitlines()[-1])["status"])
        snapshot(event)
    tick(experiment)
    tick(experiment)
    snapshot("workload_checked")
    outcome = restart_outcome(initial, timeline[-1]["state"])
    checks = {
        "approval_required": requested == "pending_operator_review"
        and not timeline[1]["state"]["worker_enabled"],
        "approval_idempotent": statuses == ["applied", "already_applied"]
        and timeline[-1]["state"]["restart_events"] == 1,
        "workload_outcome_matches_scenario": (
            outcome["workload_recovered"] is not persistent_inventory_fault
            and outcome["order_status"]
            == ("queued" if persistent_inventory_fault else "completed")
        ),
    }
    return {
        "scenario": "compound_inventory_fault"
        if persistent_inventory_fault
        else "worker_restart",
        "timeline": timeline,
        "approval_statuses": statuses,
        "outcome": outcome,
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    init_db()
    install()
    scenarios = [anyio.run(run_scenario, condition) for condition in (False, True)]
    with args.output.open("x") as destination:
        json.dump({"suite": scenarios}, destination, indent=2)
        destination.write("\n")
    return int(not all(all(row["checks"].values()) for row in scenarios))


if __name__ == "__main__":
    raise SystemExit(main())
