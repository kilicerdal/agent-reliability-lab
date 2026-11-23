"""Recompute grades and summary from the captured V2 transcripts, without API access."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from backend.lab.contracts import Diagnosis
from backend.reliability.evaluate import FIXTURES, IncidentTools, grade, summarize

ROOT = FIXTURES.parents[2]


def verify(evidence=ROOT / "evidence" / "v2", fixtures=FIXTURES):
    raw = fixtures.read_bytes()
    summary = json.loads((evidence / "summary.json").read_text())
    assert summary["fixture_sha256"] == hashlib.sha256(raw).hexdigest()
    assert summary["split"] == "holdout"
    arms = tuple(summary["arms"])
    assert arms in (("baseline", "recovery"), ("recovery", "cause-contract"))
    cases = {case["id"]: case for case in json.loads(raw) if case["split"] == "holdout"}
    rows = [
        json.loads(line) for line in (evidence / "runs.jsonl").read_text().splitlines()
    ]
    expected = Counter(
        (case, arm, repetition)
        for case in cases
        for arm in arms
        for repetition in range(1, summary["repeats"] + 1)
    )
    assert Counter((r["incident"], r["arm"], r["trial"]) for r in rows) == expected
    for row in rows:
        case = cases[row["incident"]]
        assert row["expected"] == case["cause"]
        assert row["failure"] == case["failure"]
        diagnosis = (
            Diagnosis.model_validate(row["diagnosis"]) if row["diagnosis"] else None
        )
        tools = IncidentTools(case)
        for entry in row["trace"]:
            if entry["type"] == "tool" and entry["ok"]:
                assert (
                    tools(entry["name"], json.loads(entry["arguments"]))
                    == entry["result"]
                )
        assert row["estimated_usd"] == round(
            sum(entry.get("estimated_usd", 0) for entry in row["trace"]), 6
        )
        for key, value in grade(case, diagnosis, row["trace"]).items():
            assert row[key] == value, (row["incident"], row["arm"], row["trial"], key)
    assert summarize(rows, arms) == summary["arms"]
    print(f"Verified the holdout fixture hash and {len(rows)} captured grades.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=ROOT / "evidence" / "v2")
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    args = parser.parse_args()
    verify(args.evidence, args.fixtures)
