"""Replay rules, single-model decisions, and Luna-to-Sol escalation offline."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from .quality_report import report as verify_quality


def evaluate(rows):
    pairs = defaultdict(dict)
    for row in rows:
        if row["prompt"] == "check-support":
            pairs[row["incident"], row["repeat"]][row["model"]] = row
    if not pairs or any(
        set(pair) != {"gpt-6-luna", "gpt-6.2-sol"} for pair in pairs.values()
    ):
        raise ValueError(
            "Decision replay requires aligned Luna and Sol baseline trials"
        )
    trials = []
    for (incident, repeat), pair in sorted(pairs.items()):
        luna, sol = pair["gpt-6-luna"], pair["gpt-6.2-sol"]
        luna_quality = luna["evidence_quality"]["diagnosis"]
        use_sol = not luna_quality or luna_quality["confidence"] != "confirmed"
        for policy, outcome, chain in (
            ("luna", luna, [luna]),
            ("sol", sol, [sol]),
            (
                "luna_then_sol",
                sol if use_sol else luna,
                [luna, sol] if use_sol else [luna],
            ),
        ):
            verdict = outcome["verdict"]
            trials.append(
                {
                    "incident": incident,
                    "repeat": repeat,
                    "policy": policy,
                    "correct_cause": verdict["cause_correct"],
                    "supported": verdict["passed"],
                    "abstained": (outcome["diagnosis"] or {}).get("cause") == "unknown",
                    "escalated": len(chain) > 1,
                    "estimated_ms": sum(row["elapsed_ms"] for row in chain),
                    "estimated_usd": round(
                        sum(row["estimated_usd"] for row in chain), 6
                    ),
                }
            )
        rules = luna["evidence_quality"]["rules_baseline"]["cause"]
        trials.append(
            {
                "incident": incident,
                "repeat": repeat,
                "policy": "rules_on_luna_observations",
                "correct_cause": rules == luna["expected"],
                "supported": None,
                "abstained": rules == "unknown",
                "escalated": False,
                "estimated_ms": None,
                "estimated_usd": None,
            }
        )
    summaries = {}
    for policy in ("rules_on_luna_observations", "luna", "sol", "luna_then_sol"):
        group = [trial for trial in trials if trial["policy"] == policy]
        costs = [
            trial["estimated_usd"]
            for trial in group
            if trial["estimated_usd"] is not None
        ]
        times = sorted(
            trial["estimated_ms"]
            for trial in group
            if trial["estimated_ms"] is not None
        )
        supported = (
            sum(trial["supported"] is True for trial in group) if costs else None
        )
        total_cost = sum(costs)
        summaries[policy] = {
            "runs": len(group),
            "correct_cause": sum(trial["correct_cause"] for trial in group),
            "citation_supported": supported,
            "abstained": sum(trial["abstained"] for trial in group),
            "escalated": sum(trial["escalated"] for trial in group),
            "estimated_median_ms": median(times) if times else None,
            "estimated_p95_ms": times[(95 * len(times) + 99) // 100 - 1]
            if times
            else None,
            "estimated_usd": round(total_cost, 6) if costs else None,
            "estimated_usd_per_supported": round(total_cost / supported, 6)
            if supported
            else None,
        }
    return {"mode": "recorded_policy_replay", "policies": summaries, "trials": trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in (args.capture / "runs.jsonl").read_text().splitlines()
    ]
    manifest = json.loads((args.capture / "manifest.json").read_text())
    verify_quality(rows, manifest)
    print(json.dumps(evaluate(rows), indent=2))


if __name__ == "__main__":
    main()
