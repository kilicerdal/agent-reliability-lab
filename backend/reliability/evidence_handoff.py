"""Compare fresh Sol restarts and evidence handoffs from identical recorded Luna runs."""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Event

from dotenv import load_dotenv
from openai import APIStatusError, OpenAI

from backend.lab.agent import MODEL
from backend.lab.tools import NAMES

from .assurance import SupportedDiagnosis, grade_claims
from .blind_intake import incident_dispatch, load_suite
from .live_escalation import FIXTURES
from .live_escalation import report as baseline_report
from .recovery_benchmark import run_once

BASELINE = Path("evidence/assurance/live-escalation")


def build_handoff(luna):
    observations = [
        {
            "type": "tool",
            "name": event["name"],
            "ok": True,
            "result": {"records": event["result"]["records"]},
            "phase": "handoff",
        }
        for event in luna["trace"]
        if event["type"] == "tool"
        and event.get("ok")
        and event["name"] in NAMES
        and event["result"].get("records")
    ]
    return {"provisional_diagnosis": luna["diagnosis"], "observations": observations}


def summarize(baseline, new, answers, policy):
    candidates = {row["incident"]: row for row in new}
    escalations = {row["incident"] for row in baseline if row["fallback"] is not None}
    if set(candidates) != escalations or len(candidates) != len(new):
        raise ValueError("Handoff capture does not match the baseline escalation set")
    summaries = {}
    for arm in ("restart", "handoff"):
        totals = []
        fresh_reads = 0
        execution_errors = 0
        for original in baseline:
            incident = original["incident"]
            fresh = candidates[incident][arm] if incident in candidates else None
            if fresh:
                answer = answers[incident]
                diagnosis = (
                    SupportedDiagnosis.model_validate(fresh["diagnosis"])
                    if fresh["diagnosis"]
                    else None
                )
                if (
                    grade_claims(
                        diagnosis, answer.cause, fresh["trace"], answer.judgments
                    )
                    != fresh["verdict"]
                ):
                    raise ValueError(f"Invalid diagnosis grade for {incident}/{arm}")
                expected = (
                    build_handoff(original["luna"])["observations"]
                    if arm == "handoff"
                    else []
                )
                inherited = [
                    event for event in fresh["trace"] if event.get("phase") == "handoff"
                ]
                if expected != inherited:
                    raise ValueError(f"Different initial evidence for {incident}/{arm}")
                execution_errors += fresh["error"] is not None
                fresh_reads += sum(
                    event["type"] == "tool" and event.get("phase") != "handoff"
                    for event in fresh["trace"]
                )
            output = fresh or original["luna"]
            chain = [original["luna"], fresh] if fresh else [original["luna"]]
            totals.append(
                {
                    "incident": incident,
                    "cause_correct": output["verdict"]["cause_correct"],
                    "supported": output["verdict"]["passed"],
                    "premature": output["expected"] == "unknown"
                    and (output["diagnosis"] or {}).get("cause")
                    not in {None, "unknown"},
                    "elapsed_ms": sum(row["elapsed_ms"] for row in chain),
                    "estimated_usd": sum(row["estimated_usd"] for row in chain),
                }
            )
        times = sorted(row["elapsed_ms"] for row in totals)
        summaries[arm] = {
            "runs": len(totals),
            "cause_correct": sum(row["cause_correct"] for row in totals),
            "supported": sum(row["supported"] for row in totals),
            "p95_ms": times[(95 * len(times) + 99) // 100 - 1],
            "estimated_usd": round(sum(row["estimated_usd"] for row in totals), 6),
            "estimated_fresh_usd": round(
                sum(row[arm]["estimated_usd"] for row in new), 6
            ),
            "fresh_tool_reads": fresh_reads,
            "execution_errors": execution_errors,
            "trials": totals,
        }
    sol = baseline_report(baseline, answers, policy)
    sol_summary = sol["policies"]["sol"]
    handoff = summaries["handoff"]
    handoff["checks"] = {
        "minimum_cohort": len(baseline) >= policy["minimum_incidents"],
        "cost": handoff["estimated_usd"]
        <= sol_summary["estimated_usd"] * (1 - policy["minimum_cost_savings_vs_sol"]),
        "p95_latency": handoff["p95_ms"] - sol_summary["p95_ms"]
        <= policy["maximum_p95_increase_ms_vs_sol"],
        "preserve_case_accuracy_and_support": all(
            (not prior["cause_correct"] or next_["cause_correct"])
            and (not prior["supported"] or next_["supported"])
            for prior, next_ in zip(
                sol["trials"]["sol"], handoff["trials"], strict=True
            )
        ),
        "no_premature_cause": not any(row["premature"] for row in handoff["trials"]),
        "no_execution_failures": handoff["execution_errors"] == 0,
    }
    return {
        "historical_sol": sol_summary,
        "arms": summaries,
        "eligible": all(handoff["checks"].values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    cases, answers, suite = load_suite(
        FIXTURES / "observations.json", FIXTURES / "answers.json"
    )
    policy_path = FIXTURES / "policy.json"
    policy = json.loads(policy_path.read_text())
    baseline_bytes = (BASELINE / "runs.jsonl").read_bytes()
    baseline = [json.loads(line) for line in baseline_bytes.splitlines()]
    capture = {
        "baseline_sha256": sha256(baseline_bytes).hexdigest(),
        "policy_sha256": sha256(policy_path.read_bytes()).hexdigest(),
        "suite": suite,
        "workers": 4,
    }
    selected = [row for row in baseline if row["fallback"] is not None]
    if args.replay:
        frozen = json.loads((args.output / "manifest.json").read_text())
        if any(
            frozen[field] != capture[field]
            for field in ("baseline_sha256", "policy_sha256")
        ) or any(
            frozen["suite"][field] != suite[field]
            for field in ("observations_sha256", "answer_key_sha256")
        ):
            parser.error("Frozen input digests differ")
        rows = [
            json.loads(line)
            for line in (args.output / "runs.jsonl").read_text().splitlines()
        ]
        print(json.dumps(summarize(baseline, rows, answers, policy), indent=2))
        return
    if not args.env_file:
        parser.error("A live comparison requires --env-file")
    load_dotenv(args.env_file)
    client = OpenAI(max_retries=0, timeout=10)
    original_create = client.responses.create
    stop = Event()

    def guarded(**payload):
        if stop.is_set():
            raise SystemExit(
                "Stopping new API requests after a credential or quota error"
            )
        try:
            return original_create(**payload)
        except APIStatusError as exc:
            if exc.status_code in {401, 403, 404, 429}:
                stop.set()
                raise SystemExit(
                    f"API precondition failed: HTTP {exc.status_code}, code={exc.code}"
                ) from None
            raise

    client.responses.create = guarded
    cases_by_id = {case.id: case for case in cases}

    def trial(pair):
        index, row = pair
        case = cases_by_id[row["incident"]]
        answer = answers[case.id]
        results = {"incident": case.id}
        for arm in ("restart", "handoff") if index % 2 == 0 else ("handoff", "restart"):
            results[arm] = run_once(
                client,
                MODEL,
                "check-support",
                case.alert,
                incident_dispatch(case),
                answer.cause,
                answer.judgments,
                incident=case,
                handoff=build_handoff(row["luna"]) if arm == "handoff" else None,
            )
        return results

    args.output.mkdir(parents=True)
    (args.output / "manifest.json").write_text(json.dumps(capture, indent=2) + "\n")
    rows = []
    with (
        (args.output / "runs.jsonl").open("x") as log,
        ThreadPoolExecutor(max_workers=4) as pool,
    ):
        for row in pool.map(trial, enumerate(selected)):
            rows.append(row)
            log.write(json.dumps(row) + "\n")
            log.flush()
            os.fsync(log.fileno())
            print(row["incident"], flush=True)
    (args.output / "summary.json").write_text(
        json.dumps(summarize(baseline, rows, answers, policy), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
