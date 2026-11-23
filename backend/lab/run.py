import hashlib
import json
import os
import platform
import uuid
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from .agent import investigate
from .db import init_db
from .evaluator import evaluate
from .sandbox import SCENARIOS, fingerprint, reproduce


def run(kind):
    if kind not in SCENARIOS:
        raise ValueError("Unknown scenario")
    init_db()
    e = reproduce(kind)
    before = fingerprint(e)
    diagnosis, trace, usage = investigate(e, SCENARIOS[kind]["alert"])
    after = fingerprint(e)
    source = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        source.update(path.name.encode())
        source.update(path.read_bytes())
    result = {
        "source_digest": source.hexdigest(),
        "runtime": {
            "python": platform.python_version(),
            "openai_sdk": version("openai"),
        },
        "workload_fingerprints": {"before": before, "after": after},
        "id": str(uuid.uuid4()),
        "recorded_at": datetime.now(UTC).isoformat(),
        "scenario": kind,
        "experiment": e,
        "mode": "live-model / real local workload",
        "diagnosis": diagnosis.model_dump(),
        "trace": trace,
        "usage": usage,
        "verdict": evaluate(kind, diagnosis, trace, before, after),
        "scope": "Synthetic local PostgreSQL, worker and HTTP dependency; no production systems. Oracle is separate from agent tools, not a security-isolated process.",
    }
    out = Path(os.environ.get("LAB_RESULTS_DIR", "evidence/runs"))
    out.mkdir(parents=True, exist_ok=True)
    target = out / (result["id"] + ".json")
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(result, indent=2) + "\n")
    temp.replace(target)
    return result


if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv

    p = argparse.ArgumentParser()
    p.add_argument("scenario", choices=SCENARIOS)
    p.add_argument("--env-file")
    a = p.parse_args()
    if a.env_file:
        load_dotenv(a.env_file, override=False)
    r = run(a.scenario)
    print(
        json.dumps(
            {"id": r["id"], "passed": r["verdict"]["passed"], "usage": r["usage"]}
        )
    )
