import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


@contextmanager
def connect(readonly=False):
    name = "LAB_READER_DSN" if readonly else "LAB_DATABASE_URL"
    with psycopg.connect(
        os.environ[name], row_factory=dict_row, connect_timeout=5
    ) as c:
        if readonly:
            c.execute("SET TRANSACTION READ ONLY")
        yield c


def init_db():
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS experiments (
          id text PRIMARY KEY, kind text NOT NULL, worker_enabled boolean NOT NULL,
          inventory_mode text NOT NULL, query_delay double precision NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS orders (id bigserial PRIMARY KEY, experiment text NOT NULL REFERENCES experiments(id), status text NOT NULL DEFAULT 'queued');
          CREATE TABLE IF NOT EXISTS observations (id bigserial PRIMARY KEY, experiment text NOT NULL REFERENCES experiments(id), service text NOT NULL, signal text NOT NULL, detail text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());""")
        # A distinct role is used by the tools; it cannot read fault configuration.
        c.execute(
            """DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='lab_reader') THEN CREATE ROLE lab_reader LOGIN; END IF; END $$"""
        )
        c.execute("ALTER ROLE lab_reader PASSWORD 'lab_reader'")
        c.execute("GRANT USAGE ON SCHEMA public TO lab_reader")
        c.execute("GRANT SELECT ON observations, orders TO lab_reader")
