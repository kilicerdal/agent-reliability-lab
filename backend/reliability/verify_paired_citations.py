"""Regrade the published paired citation-policy capture offline."""

import argparse
import json
from collections import Counter
from hashlib import sha256
from itertools import product
from pathlib import Path

from .assurance import EvidenceJudgment, SupportedDiagnosis, grade_claims
from .recovery_benchmark import RATES, summarize_review_policies


def verify(folder, *, announce=True):
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["rates_per_million"] == {
        model: list(rates) for model, rates in RATES.items()
    }
    observations = json.loads((folder / "observations.json").read_text())
    answers = {
        answer["id"]: answer
        for answer in json.loads((folder / "answers.json").read_text())
    }
    for filename, key in (
        ("observations.json", "observations_sha256"),
        ("answers.json", "answer_key_sha256"),
    ):
        assert (
            sha256((folder / filename).read_bytes()).hexdigest()
            == manifest["suite"][key]
        )
    assert len(observations) == len(answers) == manifest["suite"]["cases"]
    rows = [
        json.loads(line) for line in (folder / "runs.jsonl").read_text().splitlines()
    ]
    assert Counter(
        (row["incident"], row["model"], row["repeat"]) for row in rows
    ) == Counter(
        product(
            answers, manifest["rates_per_million"], range(1, manifest["repeats"] + 1)
        )
    )
    for row in rows:
        assert row["prompt"] == "verify-citations"
        answer = answers[row["incident"]]
        rubric = [EvidenceJudgment.model_validate(item) for item in answer["judgments"]]
        assert row["expected"] == answer["cause"]
        assert row["rubric"] == [item.model_dump() for item in rubric]
        before, after = (
            SupportedDiagnosis.model_validate(row[field]) if row[field] else None
            for field in ("original_diagnosis", "diagnosis")
        )
        assert (before is None) == (after is None)
        if before:
            assert before.cause == after.cause
        assert (
            grade_claims(before, answer["cause"], row["trace"], rubric)
            == row["original_verdict"]
        )
        verdict = grade_claims(after, answer["cause"], row["trace"], rubric)
        if row["citation_review"] != "accepted":
            verdict["passed"] = False
        assert verdict == row["verdict"]
        assert 0 <= row["initial_elapsed_ms"] <= row["elapsed_ms"]
        rates = RATES[row["model"]]
        for event in row["trace"]:
            if event["type"] == "model":
                assert (
                    event["estimated_usd"]
                    == (
                        event["input_tokens"] * rates[0]
                        + event["output_tokens"] * rates[1]
                    )
                    / 1_000_000
                )
        assert row["estimated_usd"] == round(
            sum(event.get("estimated_usd", 0) for event in row["trace"]), 6
        )
    assert summarize_review_policies(rows) == json.loads(
        (folder / "summary.json").read_text()
    )
    if announce:
        print(
            f"Verified {len(rows)} paired citation trials and all three policy summaries."
        )
    return manifest, rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    verify(parser.parse_args().folder)
