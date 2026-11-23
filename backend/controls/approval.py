"""One operator-approved transition for a disabled synthetic worker."""

import argparse
import json
import os
import secrets
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
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
                    CREATE ROLE lab_mcp NOLOGIN;
                END IF;
            END $$;
            ALTER ROLE lab_mcp NOLOGIN;
            ALTER TABLE worker_restart_requests ADD COLUMN IF NOT EXISTS action text
                NOT NULL DEFAULT 'restart_worker' CHECK (action = 'restart_worker');
            GRANT USAGE ON SCHEMA public TO lab_mcp;
            GRANT SELECT ON orders, observations TO lab_mcp;
            GRANT INSERT (experiment), SELECT (experiment, approved_at)
                ON worker_restart_requests TO lab_mcp;
        """)
        for table in ("orders", "observations", "worker_restart_requests"):
            identifier = sql.Identifier(table)
            conn.execute(
                sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(identifier)
            )
            conn.execute(
                sql.SQL("DROP POLICY IF EXISTS scoped_mcp ON {}").format(identifier)
            )
            conn.execute(
                sql.SQL("""
                CREATE POLICY scoped_mcp ON {} TO lab_mcp
                USING (session_user::text = 'lab_scope_' || replace(experiment, '-', ''))
                WITH CHECK (session_user::text = 'lab_scope_' || replace(experiment, '-', ''))
            """).format(identifier)
            )
        for table in ("orders", "observations"):
            identifier = sql.Identifier(table)
            conn.execute(
                sql.SQL("DROP POLICY IF EXISTS historical_reader ON {}").format(
                    identifier
                )
            )
            conn.execute(
                sql.SQL(
                    "CREATE POLICY historical_reader ON {} FOR SELECT TO lab_reader USING (true)"
                ).format(identifier)
            )


@contextmanager
def scoped_mcp_dsn(experiment):
    """Create a short-lived login for one trusted launcher session."""
    identity = UUID(experiment)
    role = "lab_scope_" + identity.hex
    password = secrets.token_urlsafe(32)
    expires = str(datetime.now(UTC) + timedelta(minutes=20))
    owner_options = conninfo_to_dict(os.environ["LAB_DATABASE_URL"])
    location = {
        key: owner_options[key]
        for key in ("host", "port", "dbname", "sslmode")
        if key in owner_options
    }
    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM experiments WHERE id=%s", (str(identity),)
        ).fetchone()
        if not exists:
            raise ValueError("Unknown experiment")
        conn.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN IN ROLE lab_mcp PASSWORD {} VALID UNTIL {}"
            ).format(sql.Identifier(role), sql.Literal(password), sql.Literal(expires))
        )
    try:
        yield make_conninfo(user=role, password=password, **location)
    finally:
        with connect() as conn:
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


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
               FROM worker_restart_requests WHERE experiment = %s AND action = 'restart_worker' FOR UPDATE""",
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
    serve = subcommands.add_parser("serve")
    serve.add_argument("experiment", type=UUID)
    approval = subcommands.add_parser("approve")
    approval.add_argument("experiment", type=UUID)
    args = parser.parse_args()
    if args.operation == "install":
        install()
        return
    experiment = str(args.experiment)
    if args.operation == "serve":
        with scoped_mcp_dsn(experiment) as dsn:
            result = subprocess.run(
                [sys.executable, "-m", "backend.controls.server", experiment],
                env={"LAB_MCP_DSN": dsn},
                check=False,
            )
        raise SystemExit(result.returncode)
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
