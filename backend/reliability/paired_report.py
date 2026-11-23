"""Summarize verified cause-contract comparisons by label, incident, and paired outcome."""

import argparse
import json
from collections import Counter
from pathlib import Path

from .agent import CAUSE_GUIDE
from .evaluate import FIXTURES
from .verify import verify

ARMS = ("recovery", "cause-contract")


def score(rows):
    pair_keys = {(row["incident"], row["trial"]) for row in rows}
    pairs = {(row["incident"], row["trial"], row["arm"]): row for row in rows}
    outcomes = Counter()
    for incident, trial in pair_keys:
        control, candidate = (
            pairs[incident, trial, arm]["strict_pass"] for arm in ARMS
        )
        outcome = {
            (True, True): "both_passed",
            (False, True): "candidate_only",
            (True, False): "control_only",
            (False, False): "both_failed",
        }[control, candidate]
        outcomes[outcome] += 1

    by_cause = {}
    for cause in CAUSE_GUIDE:
        by_cause[cause] = {
            arm: {
                "passed": sum(
                    row["strict_pass"]
                    for row in rows
                    if row["arm"] == arm and row["expected"] == cause
                ),
                "runs": sum(
                    row["arm"] == arm and row["expected"] == cause for row in rows
                ),
            }
            for arm in ARMS
        }

    by_incident = {}
    for incident in sorted({row["incident"] for row in rows}):
        by_incident[incident] = {
            arm: sum(
                row["strict_pass"]
                for row in rows
                if row["arm"] == arm and row["incident"] == incident
            )
            for arm in ARMS
        }
    net_passes = outcomes["candidate_only"] - outcomes["control_only"]
    improved = [
        cause
        for cause, arms in by_cause.items()
        if arms["cause-contract"]["passed"] > arms["recovery"]["passed"]
    ]
    regressed = [
        cause
        for cause, arms in by_cause.items()
        if arms["cause-contract"]["passed"] < arms["recovery"]["passed"]
    ]
    return {
        "paired_outcomes": dict(sorted(outcomes.items())),
        "net_strict_passes": net_passes,
        "by_cause": by_cause,
        "by_incident": by_incident,
        "improved_causes": improved,
        "regressed_causes": regressed,
        "sql_to_dependency_mislabels": {
            arm: sum(
                row["expected"] == "db_latency"
                and (row["diagnosis"] or {}).get("cause") == "dependency_config"
                for row in rows
                if row["arm"] == arm
            )
            for arm in ARMS
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verify(args.evidence, args.fixtures)
    summary = json.loads((args.evidence / "summary.json").read_text())
    if tuple(summary["arms"]) != ARMS:
        parser.error("Expected the recovery versus cause-contract comparison")
    rows = [
        json.loads(line)
        for line in (args.evidence / "runs.jsonl").read_text().splitlines()
    ]
    report = score(rows)
    report["fixture_sha256"] = summary["fixture_sha256"]
    gate_applies = summary["repeats"] == 2 and all(
        counts["runs"] == 10
        for arms in report["by_cause"].values()
        for counts in arms.values()
    )
    report["strict_pass_gate"] = (
        (
            report["net_strict_passes"] >= 3
            and "db_latency" in report["improved_causes"]
            and not report["regressed_causes"]
        )
        if gate_applies
        else None
    )
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        with args.output.open("x") as file:
            file.write(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
