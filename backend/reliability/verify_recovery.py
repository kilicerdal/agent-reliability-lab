"""Verify recovery evidence, paired coverage, support grades, and token estimates offline."""

import argparse
import json
from collections import Counter
from pathlib import Path

from .assurance import EvidenceJudgment, SupportedDiagnosis, grade_claims
from .live_challenges import SCENARIOS
from .recovery_benchmark import COST_LIMIT, LATENCY_LIMIT, RATES, summarize


def verify(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    rows = [
        json.loads(line) for line in (folder / "runs.jsonl").read_text().splitlines()
    ]
    assert manifest["rates_per_million"] == {
        key: list(value) for key, value in RATES.items()
    }
    assert manifest["limits"] == {
        "elapsed_seconds": LATENCY_LIMIT,
        "estimated_usd": COST_LIMIT,
    }
    assert set(manifest["suite"]) == SCENARIOS.keys()
    prompts = (
        ("check-support", "verify-citations")
        if manifest.get("citation_review")
        else ("basic-citations", "check-support")
    )
    coverage = Counter(
        (row["incident"], row["repeat"], row["model"], row["prompt"]) for row in rows
    )
    assert coverage == Counter(
        (incident, repeat, model, prompt)
        for incident in SCENARIOS
        for repeat in range(1, manifest["repeats"] + 1)
        for model in RATES
        for prompt in prompts
    )
    for row in rows:
        assert row["expected"] == SCENARIOS[row["incident"]][1]
        diagnosis = (
            SupportedDiagnosis.model_validate(row["diagnosis"])
            if row["diagnosis"]
            else None
        )
        rubric = [EvidenceJudgment.model_validate(entry) for entry in row["rubric"]]
        verdict = grade_claims(diagnosis, row["expected"], row["trace"], rubric)
        if row["prompt"] == "verify-citations":
            original = row["original_diagnosis"]
            assert (original is None) == (diagnosis is None)
            if original:
                assert original["cause"] == diagnosis.cause
            review_events = [
                event
                for event in row["trace"]
                if event.get("phase") == "citation_review"
            ]
            assert len(review_events) <= 1
            assert all(event["type"] == "model" for event in review_events)
            if row["citation_review"] == "accepted":
                assert original and len(review_events) == 1
            else:
                verdict["passed"] = False
                assert original == row["diagnosis"]
        assert row["verdict"] == verdict
        rates = RATES[row["model"]]
        for event in row["trace"]:
            if event["type"] == "model":
                assert event["model"] == row["model"]
                assert (
                    event["estimated_usd"]
                    == (
                        event["input_tokens"] * rates[0]
                        + event["output_tokens"] * rates[1]
                    )
                    / 1_000_000
                )
        assert row["estimated_usd"] == round(
            sum(entry.get("estimated_usd", 0) for entry in row["trace"]), 6
        )
        assert row["within_limits"] == (
            row["error"] is None
            and row["elapsed_ms"] <= LATENCY_LIMIT * 1000
            and row["estimated_usd"] <= COST_LIMIT
        )
        assert row["unchanged_workload"]
        timeouts = [
            event
            for event in row["trace"]
            if event["type"] == "tool" and event["result"].get("error") == "timeout"
        ]
        observed = row["injected_timeouts_observed"]
        assert len(timeouts) == len(observed) <= 1
        for event in observed:
            assert (row["incident"], event) in {
                ("http-timeout", "http_read_timeout"),
                ("sql-timeout", "postgres_statement_timeout"),
            }
    assert summarize(rows) == json.loads((folder / "summary.json").read_text())
    print(
        f"Verified {len(rows)} recovery grades, paired coverage, workload checks and cost estimates."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    verify(parser.parse_args().folder)


if __name__ == "__main__":
    main()
