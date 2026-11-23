"""Compare model and citation prompts on the same isolated recovery cases."""

import argparse
import json
import time
from collections import defaultdict
from functools import partial
from pathlib import Path
from statistics import median

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import ValidationError

from backend.lab.agent import MODEL, PROMPT
from backend.lab.budget import Budget, BudgetExceeded
from backend.lab.db import init_db
from backend.lab.sandbox import fingerprint

from .agent import investigate
from .assurance import SupportedDiagnosis, grade_claims
from .blind_intake import dispatch_observations, load_suite
from .live_challenges import SCENARIOS, LiveChallenge

RATES = {MODEL: (2, 10), "gpt-6-luna": (0.1, 0.5)}
LATENCY_LIMIT = 25.0
COST_LIMIT = 0.03
CITATION_INSTRUCTIONS = (
    " Return separate claims for mechanism and configuration. Each claim needs "
    "an evidence_id listed in evidence_ids and an exact quotation from its detail."
)
CHECK_SUPPORT = (
    " For each claim check that the quote supports the chosen cause directly. "
    "Prefer current evidence and verify agreement between workload and configuration. "
    "For unknown, cite the specific gaps that prevent a diagnosis."
)


def run_once(client, model, check_support, alert, tools, answer, rubric):
    trace = []
    diagnosis = None
    error = None
    start = time.monotonic()
    try:
        diagnosis, _, _ = investigate(
            alert,
            tools,
            client,
            Budget(rates=RATES[model]),
            improved=True,
            trace=trace,
            response_model=SupportedDiagnosis,
            model=model,
            deadline=start + LATENCY_LIMIT,
            max_requests=6,
            instructions=PROMPT
            + CITATION_INSTRUCTIONS
            + (CHECK_SUPPORT if check_support else ""),
        )
    except (
        APIConnectionError,
        APIStatusError,
        ValidationError,
        RuntimeError,
        TimeoutError,
    ) as exc:
        if isinstance(exc, BudgetExceeded):
            raise
        error = type(exc).__name__
    elapsed = time.monotonic() - start
    cost = round(sum(event.get("estimated_usd", 0) for event in trace), 6)
    verdict = grade_claims(diagnosis, answer, trace, rubric)
    return {
        "model": model,
        "prompt": "check-support" if check_support else "basic-citations",
        "diagnosis": diagnosis.model_dump() if diagnosis else None,
        "error": error,
        "expected": answer,
        "verdict": verdict,
        "trace": trace,
        "estimated_usd": cost,
        "elapsed_ms": round(elapsed * 1000),
        "within_limits": error is None
        and elapsed <= LATENCY_LIMIT
        and cost <= COST_LIMIT,
    }


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[f"{row['model']}/{row['prompt']}"].append(row)
    return {
        arm: {
            "runs": len(group),
            "correct_cause": sum(row["verdict"]["cause_correct"] for row in group),
            "supported": sum(row["verdict"]["passed"] for row in group),
            "within_limits": sum(row["within_limits"] for row in group),
            "errors": sum(row["error"] is not None for row in group),
            "median_ms": median(row["elapsed_ms"] for row in group),
            "estimated_usd": round(sum(row["estimated_usd"] for row in group), 6),
        }
        for arm, group in groups.items()
    }


def run_suite(client, output, cases, repeats, *, live):
    rows = []
    arms = [(model, support) for model in RATES for support in (False, True)]
    with (output / "runs.jsonl").open("x") as log:
        for repeat in range(1, repeats + 1):
            for index, case in enumerate(cases):
                for model, support in arms if (index + repeat) % 2 else reversed(arms):
                    if live:
                        tools, events = case.tools()
                        before = fingerprint(case.experiment)
                        alert, answer, rubric, name = (
                            case.alert,
                            case.cause,
                            case.rubric,
                            case.name,
                        )
                    else:
                        incident, review = case
                        tools = partial(dispatch_observations, incident)
                        alert, answer, rubric, name = (
                            incident.alert,
                            review.cause,
                            review.judgments,
                            incident.id,
                        )
                    row = run_once(client, model, support, alert, tools, answer, rubric)
                    if live:
                        row["injected_timeouts_observed"] = events
                        row["unchanged_workload"] = before == fingerprint(
                            case.experiment
                        )
                    row.update(
                        incident=name,
                        repeat=repeat,
                        rubric=[item.model_dump() for item in rubric],
                    )
                    rows.append(row)
                    log.write(json.dumps(row) + "\n")
                    log.flush()
                    print(
                        name,
                        repeat,
                        model,
                        row["prompt"],
                        row["verdict"]["passed"],
                        row["error"],
                        flush=True,
                    )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--sealed", type=Path)
    parser.add_argument("--repeats", type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    intake = (args.cases, args.key, args.sealed)
    if any(intake) and not all(intake):
        parser.error("Provide the independent cases, answer key, and sealed manifest")
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    external = args.cases is not None
    if external:
        observations, key, manifest = load_suite(args.cases, args.key)
        if json.loads(args.sealed.read_text()) != manifest:
            parser.error(
                "Observations, answer key, or prompt protocol changed after sealing"
            )
        cases = [(case, key[case.id]) for case in observations]
    else:
        init_db()
        cases = [LiveChallenge(name) for name in SCENARIOS]
        manifest = {case.name: fingerprint(case.experiment) for case in cases}
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "manifest.json").open("x") as output:
        json.dump(
            {
                "suite": manifest,
                "repeats": args.repeats,
                "rates_per_million": RATES,
                "limits": {
                    "elapsed_seconds": LATENCY_LIMIT,
                    "estimated_usd": COST_LIMIT,
                },
            },
            output,
            indent=2,
        )
    rows = run_suite(
        OpenAI(max_retries=0, timeout=10),
        args.output,
        cases,
        args.repeats,
        live=not external,
    )
    (args.output / "summary.json").write_text(
        json.dumps(summarize(rows), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
