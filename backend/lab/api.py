"""Public-facing API serves recorded evidence only; paid runs use the local CLI."""

import json
import os
from pathlib import Path

from fastapi import FastAPI

from .sandbox import SCENARIOS

app = FastAPI(title="Agent Reliability Lab", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok", "paid_requests_from_dashboard": False}


@app.get("/scenarios")
def scenarios():
    return [
        {"id": k, "title": v["title"], "alert": v["alert"]}
        for k, v in SCENARIOS.items()
    ]


@app.get("/runs")
def runs():
    root = Path(os.environ.get("LAB_RESULTS_DIR", "evidence/runs"))
    captures = [json.loads(p.read_text()) for p in root.glob("*.json")]
    return sorted(captures, key=lambda capture: capture["recorded_at"], reverse=True)[
        :50
    ]
