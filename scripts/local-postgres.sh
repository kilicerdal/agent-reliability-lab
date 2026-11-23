#!/usr/bin/env bash
set -euo pipefail
# Optional macOS convenience. No existing PostgreSQL installation is modified.
TASK_PG_BIN="${TASK_PG_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
TASK_PG_DIR="${TASK_PG_DIR:-$PWD/.private/postgres}"
mkdir -p "$TASK_PG_DIR" "$PWD/.private/socket"
if [ ! -f "$TASK_PG_DIR/PG_VERSION" ]; then "$TASK_PG_BIN/initdb" -D "$TASK_PG_DIR" -U lab -A trust; fi
"$TASK_PG_BIN/pg_ctl" -D "$TASK_PG_DIR" -l "$PWD/.private/postgres.log" -o "-h 127.0.0.1 -p 5544 -k $PWD/.private/socket" start
"$TASK_PG_BIN/createdb" -h 127.0.0.1 -p 5544 -U lab lab || true
