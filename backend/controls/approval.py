"""One operator-approved transition for a disabled synthetic worker."""

import argparse
import json
import os
import sys
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from backend.lab.db import connect, init_db
from backend.lab.sandbox import record


def install():
    init_db()
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS worker_restart_requests (
                experiment text PRIMARY KEY REFERENCES experiments(id),
                requested_at timestamptz NOT NULL DEFAULT now(),
                approved_at timestamptz
            );
            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='lab_mcp') THEN
                    CREATE ROLE lab_mcp LOGIN PASSWORD 'lab_mcp';
                END IF;
            END $$;
            GRANT USAGE ON SCHEMA public TO lab_mcp;
            GRANT SELECT ON orders, observations TO lab_mcp;
            GRANT INSERT (experiment), SELECT (experiment, approved_at)
                ON worker_restart_requests TO lab_mcp;
        """)


def request_restart(experiment):
    with psycopg.connect(
        os.environ["LAB_READER_DSN"], row_factory=dict_row, connect_timeout=5
    ) as conn:
        conn.execute(
            """INSERT INTO worker_restart_requests (experiment) VALUES (%s)
            ON CONFLICT (experiment) DO NOTHING""",
            (experiment,),
        )
        result = conn.execute(
            """SELECT approved_at IS NOT NULL AS applied
            FROM worker_restart_requests WHERE experiment = %s""",
            (experiment,),
        ).fetchone()
    return {
        "request_id": experiment,
        "status": "applied" if result["applied"] else "pending_operator_review",
    }


def approve_restart(experiment):
    """Execute with the operator credential after explicit confirmation."""
    with connect() as conn:
        request = conn.execute(
            """SELECT approved_at IS NOT NULL AS applied,
                      requested_at + interval '15 minutes' <= now() AS expired
               FROM worker_restart_requests WHERE experiment = %s FOR UPDATE""",
            (experiment,),
        ).fetchone()
        if request is None:
            return "no_request"
        if request["applied"]:
            return "already_applied"
        if request["expired"]:
            return "expired"
        changed = conn.execute(
            """UPDATE experiments SET worker_enabled = true
               WHERE id = %s AND kind = 'worker-failure' AND NOT worker_enabled
               RETURNING id""",
            (experiment,),
        ).fetchone()
        if changed is None:
            return "ineligible"
        conn.execute(
            """UPDATE worker_restart_requests SET approved_at = now()
               WHERE experiment = %s""",
            (experiment,),
        )
        record(
            conn,
            experiment,
            "worker",
            "operator_restart_applied",
            "Operator approved re-enabling the synthetic worker.",
        )
        return "applied"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="operation", required=True)
    subcommands.add_parser("install")
    approval = subcommands.add_parser("approve")
    approval.add_argument("experiment", type=UUID)
    args = parser.parse_args()
    if args.operation == "install":
        install()
        return
    experiment = str(args.experiment)
    print(
        f"Action: re-enable the synthetic worker for experiment {experiment}.",
        file=sys.stderr,
    )
    print("Type the experiment ID to approve: ", end="", file=sys.stderr, flush=True)
    if sys.stdin.readline().strip() != experiment:
        parser.exit(2, "Confirmation did not match. Approval cancelled.\n")
    print(json.dumps({"request_id": experiment, "status": approve_restart(experiment)}))


if __name__ == "__main__":
    main()
