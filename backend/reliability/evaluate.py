"""Repeated live-model evaluations against frozen synthetic tool transcripts."""

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from backend.lab.budget import Budget, BudgetExceeded
from backend.lab.tools import NAMES

from .agent import investigate

FIXTURES = Path(__file__).with_name("incidents.json")


class IncidentTools:
    def __init__(self, case):
        self.case = case
        self.calls = {}

    def __call__(self, name, args):
        if name not in NAMES or args != {}:
            raise ValueError("Tool or arguments not permitted")
        self.calls[name] = self.calls.get(name, 0) + 1
        case = self.case
        failure = case["failure"] if name == case["tool"] else "none"
        if failure == "timeout" and self.calls[name] == 1:
            return {"error": "timeout", "retryable": True}
        if failure == "missing":
            return {"status": "unavailable", "records": []}

        workload = {
            "evidence_id": "obs-1",
            "signal": "workload",
            "freshness": "current",
            "detail": case["signal"],
        }
        configuration = {
            "evidence_id": "obs-2",
            "signal": "configuration",
            "freshness": "current",
            "detail": case["setting"],
        }
        records = {
            "read_logs": [workload, configuration],
            "read_deployments": [configuration],
            "read_health": [workload],
            "read_queue": [],
        }[name]
        if failure == "conflict":
            records = [
                {
                    "evidence_id": "obs-3",
                    "signal": "historical_summary",
                    "freshness": "previous deployment",
                    "detail": "A cached dashboard attributed a backlog to slow SQL.",
                }
            ]
        return {"records": records}


def grade(case, diagnosis, trace):
    tool_calls = [entry for entry in trace if entry["type"] == "tool"]
    observed = {
        record["evidence_id"]
        for entry in tool_calls
        if entry["ok"]
        for record in entry["result"].get("records", [])
    }
    citations = set(diagnosis.evidence_ids) if diagnosis else set()
    correct = diagnosis is not None and diagnosis.cause == case["cause"]
    grounded = correct and {"obs-1", "obs-2"} <= citations <= observed
    denied = any(not entry["ok"] for entry in tool_calls)
    exposed = any(
        entry["name"] == case["tool"] and entry["ok"] for entry in tool_calls
    ) and case["failure"] in {"timeout", "missing", "conflict"}
    retried = (
        case["failure"] == "timeout"
        and sum(entry["name"] == case["tool"] and entry["ok"] for entry in tool_calls)
        >= 2
    )
    return {
        "correct_cause": correct,
        "strict_pass": grounded and not denied,
        "failure_exposed": exposed,
        "recovered": exposed and grounded and not denied,
        "retried_timeout": retried,
        "denied_tool": denied,
    }


def trial(case, number, arm, client, budget):
    trace = []
    started = time.monotonic()
    diagnosis = None
    error = None
    try:
        diagnosis, _, _ = investigate(
            case["alert"],
            IncidentTools(case),
            client,
            budget,
            improved=arm != "baseline",
            cause_contract=arm == "cause-contract",
            trace=trace,
        )
    except (ValidationError, RuntimeError) as exc:
        if isinstance(exc, BudgetExceeded):
            raise
        error = type(exc).__name__
    return {
        "incident": case["id"],
        "failure": case["failure"],
        "trial": number,
        "arm": arm,
        "expected": case["cause"],
        "diagnosis": diagnosis.model_dump() if diagnosis else None,
        "error": error,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "estimated_usd": round(sum(e.get("estimated_usd", 0) for e in trace), 6),
        "trace": trace,
        **grade(case, diagnosis, trace),
    }


def summarize(rows, arms=("baseline", "recovery")):
    summaries = {}
    for arm in arms:
        runs = [row for row in rows if row["arm"] == arm]
        groups = {"all": runs}
        for failure in sorted({row["failure"] for row in runs}):
            groups[failure] = [row for row in runs if row["failure"] == failure]
        summaries[arm] = {
            name: {
                "runs": len(group),
                **{
                    key: sum(row[key] for row in group)
                    for key in (
                        "correct_cause",
                        "strict_pass",
                        "failure_exposed",
                        "recovered",
                        "retried_timeout",
                        "denied_tool",
                    )
                },
                "errors": sum(bool(row["error"]) for row in group),
                "estimated_usd": round(sum(row["estimated_usd"] for row in group), 6),
                "median_ms": median(row["elapsed_ms"] for row in group),
            }
            for name, group in groups.items()
        }
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "holdout"), required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--compare", choices=("v2", "cause-contract"), default="v2")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        parser.error("--repeats must be between 1 and 5")
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    raw = args.fixtures.read_bytes()
    cases = [case for case in json.loads(raw) if case["split"] == args.split]
    arms = (
        ("recovery", "cause-contract")
        if args.compare == "cause-contract"
        else ("baseline", "recovery")
    )
    if not cases:
        parser.error("No fixtures match the selected split")
    rows = []
    budget = Budget()
    client = OpenAI(max_retries=0, timeout=45)
    args.output.mkdir(parents=True, exist_ok=True)
    with (
        (args.output / "runs.jsonl").open("x") as output,
        ThreadPoolExecutor(max_workers=4) as executor,
    ):

        def run_trial(job):
            return trial(*job, client, budget)

        jobs = (
            (case, number, arm)
            for number in range(1, args.repeats + 1)
            for index, case in enumerate(cases)
            for arm in (arms if (index + number) % 2 else reversed(arms))
        )
        for row in executor.map(run_trial, jobs):
            rows.append(row)
            output.write(json.dumps(row) + "\n")
            output.flush()
            print(
                row["incident"],
                row["trial"],
                row["arm"],
                row["strict_pass"],
                flush=True,
            )
    summary = {
        "split": args.split,
        "repeats": args.repeats,
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "arms": summarize(rows, arms),
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
