"""Run and regrade live Luna-to-Sol escalation on a frozen synthetic cohort."""

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Event

from dotenv import load_dotenv
from openai import APIStatusError, OpenAI

from backend.lab.agent import MODEL

from .assurance import SupportedDiagnosis, grade_claims
from .blind_intake import incident_dispatch, load_suite
from .recovery_benchmark import run_once

LUNA = "gpt-6-luna"
FIXTURES = Path(__file__).with_name("escalation-fixtures")


def should_escalate(row):
    quality = row["evidence_quality"]["diagnosis"]
    return quality is None or quality["confidence"] != "confirmed"


def report(rows, key, policy):
    if Counter(row["incident"] for row in rows) != Counter(key.keys()):
        raise ValueError("Capture has missing or duplicate incidents")
    groups = {"luna": [], "sol": [], "luna_then_sol": []}
    errors = 0
    missed = 0
    for row in rows:
        answer = key[row["incident"]]
        luna, sol, fallback = row["luna"], row["sol"], row["fallback"]
        if (fallback is not None) != should_escalate(luna):
            raise ValueError(f"Unexpected escalation decision for {row['incident']}")
        for expected_model, run in ((LUNA, luna), (MODEL, sol), (MODEL, fallback)):
            if run is None:
                continue
            diagnosis = (
                SupportedDiagnosis.model_validate(run["diagnosis"])
                if run["diagnosis"]
                else None
            )
            if (
                run["model"] != expected_model
                or run["expected"] != answer.cause
                or grade_claims(diagnosis, answer.cause, run["trace"], answer.judgments)
                != run["verdict"]
            ):
                raise ValueError(f"Invalid captured run for {row['incident']}")
            if run["estimated_usd"] != round(
                sum(event.get("estimated_usd", 0) for event in run["trace"]), 6
            ):
                raise ValueError(f"Inconsistent cost for {row['incident']}")
            errors += run["error"] is not None
        missed += (
            fallback is None
            and not luna["verdict"]["passed"]
            and sol["verdict"]["passed"]
        )
        for name, output, chain in (
            ("luna", luna, [luna]),
            ("sol", sol, [sol]),
            (
                "luna_then_sol",
                fallback or luna,
                [luna, fallback] if fallback else [luna],
            ),
        ):
            cause = (output["diagnosis"] or {}).get("cause")
            groups[name].append(
                {
                    "incident": row["incident"],
                    "expected": answer.cause,
                    "returned": cause,
                    "cause_correct": output["verdict"]["cause_correct"],
                    "supported": output["verdict"]["passed"],
                    "elapsed_ms": sum(run["elapsed_ms"] for run in chain),
                    "estimated_usd": round(
                        sum(run["estimated_usd"] for run in chain), 6
                    ),
                }
            )
    summaries = {}
    for name, trials in groups.items():
        times = sorted(row["elapsed_ms"] for row in trials)
        summaries[name] = {
            "runs": len(trials),
            "cause_correct": sum(row["cause_correct"] for row in trials),
            "supported": sum(row["supported"] for row in trials),
            "premature_causes": sum(
                row["expected"] == "unknown"
                and row["returned"] not in {None, "unknown"}
                for row in trials
            ),
            "p95_ms": times[(95 * len(times) + 99) // 100 - 1],
            "estimated_usd": round(sum(row["estimated_usd"] for row in trials), 6),
        }
    escalated = summaries["luna_then_sol"]
    sol_summary = summaries["sol"]
    savings = (
        1 - escalated["estimated_usd"] / sol_summary["estimated_usd"]
        if sol_summary["estimated_usd"]
        else 0
    )
    checks = {
        "minimum_cohort": len(rows) >= policy["minimum_incidents"],
        "cost": savings >= policy["minimum_cost_savings_vs_sol"],
        "p95_latency": escalated["p95_ms"] - sol_summary["p95_ms"]
        <= policy["maximum_p95_increase_ms_vs_sol"],
        "preserve_case_accuracy_and_support": not policy[
            "require_no_case_regression_vs_sol"
        ]
        or all(
            (not baseline["cause_correct"] or candidate["cause_correct"])
            and (not baseline["supported"] or candidate["supported"])
            for baseline, candidate in zip(
                groups["sol"], groups["luna_then_sol"], strict=True
            )
        ),
        "no_premature_cause": not policy[
            "require_no_incorrect_known_cause_on_unknown_cases"
        ]
        or escalated["premature_causes"] == 0,
        "no_execution_failures": not policy["require_no_execution_failures"]
        or errors == 0,
    }
    return {
        "policies": summaries,
        "checks": checks,
        "eligible": all(checks.values()),
        "escalations": sum(row["fallback"] is not None for row in rows),
        "missed_escalations": missed,
        "cost_savings_vs_sol": round(savings, 4),
        "estimated_live_usd": round(
            sum(
                run["estimated_usd"]
                for row in rows
                for field in ("luna", "sol", "fallback")
                if (run := row[field]) is not None
            ),
            6,
        ),
        "trials": groups,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--seal", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    cases, key, manifest = load_suite(
        FIXTURES / "observations.json", FIXTURES / "answers.json"
    )
    policy_bytes = (FIXTURES / "policy.json").read_bytes()
    policy = json.loads(policy_bytes)
    manifest.update(
        policy_sha256=sha256(policy_bytes).hexdigest(),
        runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        workers=4,
    )
    if args.replay:
        frozen = json.loads((args.output / "manifest.json").read_text())
        for field in ("observations_sha256", "answer_key_sha256", "policy_sha256"):
            if manifest[field] != frozen[field]:
                parser.error(f"Frozen {field} differs from capture")
        rows = [
            json.loads(line)
            for line in (args.output / "runs.jsonl").read_text().splitlines()
        ]
        print(json.dumps(report(rows, key, policy), indent=2))
        return
    if not args.env_file or not args.seal:
        parser.error("A live run requires --env-file and --seal")
    if json.loads(args.seal.read_text()) != manifest:
        parser.error("Suite, runner, or decision criteria changed since sealing")
    load_dotenv(args.env_file)
    client = OpenAI(max_retries=0, timeout=10)
    stop = Event()
    create = client.responses.create

    def guarded(**payload):
        if stop.is_set():
            raise SystemExit("API precondition failed; no new requests")
        try:
            return create(**payload)
        except APIStatusError as exc:
            if exc.status_code in {401, 403, 404, 429}:
                stop.set()
                raise SystemExit(
                    f"API precondition failed: HTTP {exc.status_code}, code={exc.code}"
                ) from None
            raise

    client.responses.create = guarded

    def trial(index_case):
        index, case = index_case
        answer = key[case.id]

        def diagnosis(model):
            return run_once(
                client,
                model,
                "check-support",
                case.alert,
                incident_dispatch(case),
                answer.cause,
                answer.judgments,
                incident=case,
            )

        sol = diagnosis(MODEL) if index % 2 == 0 else None
        luna = diagnosis(LUNA)
        fallback = diagnosis(MODEL) if should_escalate(luna) else None
        if sol is None:
            sol = diagnosis(MODEL)
        return {"incident": case.id, "luna": luna, "sol": sol, "fallback": fallback}

    args.output.mkdir(parents=True)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    with (
        (args.output / "runs.jsonl").open("x") as log,
        ThreadPoolExecutor(max_workers=4) as pool,
    ):
        for row in pool.map(trial, enumerate(cases)):
            rows.append(row)
            log.write(json.dumps(row) + "\n")
            log.flush()
            print(f"{len(rows)}/{len(cases)} {row['incident']}", flush=True)
    (args.output / "summary.json").write_text(
        json.dumps(report(rows, key, policy), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
