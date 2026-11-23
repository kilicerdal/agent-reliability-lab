#!/usr/bin/env bash
set -euo pipefail
# Explicit paid action. Caller supplies OPENAI_API_KEY or an existing env-file path.
for incident in database-slowdown worker-failure dependency-failure healthy; do
  PYTHONPATH=backend .venv/bin/python -m lab.run "$incident" "$@"
done
