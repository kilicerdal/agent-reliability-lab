"""Capture real MCP, PostgreSQL, and synthetic worker behavior."""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anyio
import psycopg
from mcp import Client, StdioServerParameters

from backend.lab.db import connect
from backend.lab.sandbox import fingerprint, record, reproduce, tick

from .approval import approve_restart, install
from .server import REQUEST


def mcp_client(experiment):
    return Client(
        StdioServerParameters(
            command=sys.executable,
            args=["-m", "backend.controls.server", experiment],
            env={"LAB_MCP_DSN": os.environ["LAB_MCP_DSN"]},
        ),
        read_timeout_seconds=15,
    )


def state(experiment):
    with connect() as conn:
        return conn.execute(
            """SELECT e.worker_enabled,
               (SELECT status FROM orders WHERE experiment=e.id) AS order_status,
               (SELECT count(*) FROM observations WHERE experiment=e.id
                AND signal='operator_restart_applied') AS restart_events,
               (SELECT count(*) FROM observations WHERE experiment=e.id
                AND signal='order_completed') AS completion_events
               FROM experiments e WHERE e.id=%s""",
            (experiment,),
        ).fetchone()


def operator_cli(experiment, answer):
    return subprocess.run(
        [sys.executable, "-m", "backend.controls.approval", "approve", experiment],
        input=f"{answer}\n",
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )


def sqlstate(statement, experiment):
    try:
        with (
            psycopg.connect(os.environ["LAB_MCP_DSN"], connect_timeout=5) as conn,
            conn.transaction(force_rollback=True),
        ):
            conn.execute(statement, (experiment,))
    except psycopg.errors.InsufficientPrivilege as exc:
        return exc.sqlstate
    return "allowed"


async def capture():
    install()
    target = reproduce("worker-failure")
    other = reproduce("worker-failure")
    with connect() as conn:
        record(conn, other, "worker", "scope_control", "LAB_OTHER_EXPERIMENT")
    untouched = fingerprint(other)
    initial = state(target)
    before_request = approve_restart(target)
    denied = {}
    async with mcp_client(target) as client:
        catalog = await client.list_tools()
        protocol = client.protocol_version
        logs = await client.call_tool("read_logs", {})
        if logs.is_error or logs.structured_content is None:
            raise RuntimeError("Could not read scoped logs")
        for tool, args in [
            ("read_logs", {"experiment": other}),
            (REQUEST, {"experiment": other}),
            (REQUEST, {"approved": True}),
            ("approve_worker_restart", {}),
        ]:
            response = await client.call_tool(tool, args)
            denied[f"{tool}:{','.join(args)}"] = response.is_error
        requested = await client.call_tool(REQUEST, {})
        repeated = await client.call_tool(REQUEST, {})
    pending = state(target)
    denied_sql = {
        "update_worker": sqlstate(
            "UPDATE experiments SET worker_enabled=true WHERE id=%s", target
        ),
        "forge_approval": sqlstate(
            "UPDATE worker_restart_requests SET approved_at=now() WHERE experiment=%s",
            target,
        ),
    }
    wrong_confirmation = operator_cli(target, other)
    still_pending = state(target)

    # Submit two approvals together to exercise the row lock and idempotency.
    def review(_):
        outcome = operator_cli(target, target)
        outcome.check_returncode()
        return json.loads(outcome.stdout.splitlines()[-1])["status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        approved = sorted(pool.map(review, range(2)))
    enabled = state(target)
    tick(target)
    tick(target)
    completed = state(target)
    async with mcp_client(target) as client:
        await client.list_tools()
        retry_after_approval = await client.call_tool(REQUEST, {})

    stale = reproduce("worker-failure")
    async with mcp_client(stale) as client:
        await client.list_tools()
        await client.call_tool(REQUEST, {})
    with connect() as conn:
        conn.execute(
            "UPDATE worker_restart_requests SET requested_at=now()-interval '16 min' WHERE experiment=%s",
            (stale,),
        )
    expired = approve_restart(stale)
    expected_pending = {"request_id": target, "status": "pending_operator_review"}
    checks = {
        "approval_tool_absent": {t.name for t in catalog.tools}
        == {"read_logs", "read_deployments", "read_health", "read_queue", REQUEST},
        "scope_enforced": "LAB_OTHER_EXPERIMENT"
        not in json.dumps(logs.structured_content)
        and all(denied.values()),
        "no_write_privilege": set(denied_sql.values()) == {"42501"},
        "no_approval_without_request": before_request == "no_request",
        "request_retry_idempotent": requested.structured_content
        == repeated.structured_content
        == expected_pending,
        "worker_unchanged_pending": initial == pending == still_pending
        and not initial["worker_enabled"]
        and initial["order_status"] == "queued",
        "incorrect_confirmation_denied": wrong_confirmation.returncode == 2,
        "concurrent_approval_applies_once": approved == ["already_applied", "applied"]
        and enabled["worker_enabled"]
        and enabled["restart_events"] == 1,
        "worker_completed_order_once": completed["order_status"] == "completed"
        and completed["completion_events"] == 1
        and completed["restart_events"] == 1,
        "post_approval_request_retry": retry_after_approval.structured_content
        == {"status": "applied", "request_id": target},
        "request_expired": expired == "expired" and not state(stale)["worker_enabled"],
        "other_experiment_unchanged": untouched == fingerprint(other),
    }
    return {
        "scope": "synthetic PostgreSQL and HTTP inventory, MCP stdio, scripted operator confirmation",
        "protocol": protocol,
        "target": target,
        "other_experiment": other,
        "tools": [tool.name for tool in catalog.tools],
        "denied_mcp_calls": denied,
        "denied_database_sqlstates": denied_sql,
        "approvals_without_request": before_request,
        "requested": requested.structured_content,
        "request_retry": repeated.structured_content,
        "wrong_confirmation_exit": wrong_confirmation.returncode,
        "concurrent_results": approved,
        "expired_result": expired,
        "after_apply_retry": retry_after_approval.structured_content,
        "states": {
            "before_request": initial,
            "pending": pending,
            "after_wrong_confirmation": still_pending,
            "after_approval": enabled,
            "after_two_ticks": completed,
        },
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = anyio.run(capture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    if not all(result["checks"].values()):
        raise SystemExit("V3 boundary checks failed")
    print(f"{len(result['checks'])} boundary checks passed.")


if __name__ == "__main__":
    main()
