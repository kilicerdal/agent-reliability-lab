"""Summarize complete recorded selective-review trials without model calls."""

import argparse
import json
from collections import Counter
from itertools import product
from math import sqrt
from pathlib import Path

from .assurance import EvidenceJudgment, SupportedDiagnosis, grade_claims
from .recovery_benchmark import RATES, summarize

POLICIES = ("check-support", "selective-citations")


def rate(passed, total):
    proportion = passed / total
    z = 1.96
    adjustment = 1 + z**2 / total
    center = (proportion + z**2 / (2 * total)) / adjustment
    margin = (
        z
        * sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2))
        / adjustment
    )
    return {
        "passed": passed,
        "runs": total,
        "wilson_95": [
            round(max(0, center - margin), 4),
            round(min(1, center + margin), 4),
        ],
    }


def report(rows, manifest):
    coverage = Counter(
        (row["incident"], row["repeat"], row["model"], row["prompt"]) for row in rows
    )
    incidents = sorted({row["incident"] for row in rows})
    expected = Counter(
        product(incidents, range(1, manifest["repeats"] + 1), RATES, POLICIES)
    )
    if len(incidents) != manifest["suite"]["cases"] or coverage != expected:
        raise ValueError("Selective capture is incomplete or contains duplicate trials")
    for row in rows:
        diagnosis = (
            SupportedDiagnosis.model_validate(row["diagnosis"])
            if row["diagnosis"]
            else None
        )
        rubric = [EvidenceJudgment.model_validate(item) for item in row["rubric"]]
        grade = grade_claims(diagnosis, row["expected"], row["trace"], rubric)
        if row["prompt"] == "selective-citations":
            original = (
                SupportedDiagnosis.model_validate(row["original_diagnosis"])
                if row["original_diagnosis"]
                else None
            )
            initial = grade_claims(original, row["expected"], row["trace"], rubric)
            if initial != row["original_verdict"] or (
                original and original.cause != diagnosis.cause
            ):
                raise ValueError(
                    "A paired selective trial has a mismatched initial diagnosis"
                )
            if row["citation_review"] not in {"accepted", "skipped"}:
                grade["passed"] = False
        if grade != row["verdict"]:
            raise ValueError("A recorded grade disagrees with the rubric")
    summaries = summarize(rows)
    for arm, totals in summaries.items():
        model, policy = arm.split("/")
        cohort = [
            row for row in rows if row["model"] == model and row["prompt"] == policy
        ]
        totals["support_coverage"] = rate(totals["supported"], len(cohort))
        totals["support_by_cause"] = {}
        for cause in sorted({row["expected"] for row in cohort}):
            group = [row for row in cohort if row["expected"] == cause]
            totals["support_by_cause"][cause] = rate(
                sum(row["verdict"]["passed"] for row in group), len(group)
            )
        totals["rules_correct_on_observed_evidence"] = sum(
            row["evidence_quality"]["rules_baseline"]["cause"] == row["expected"]
            for row in cohort
        )
        totals["correct_unknown"] = sum(
            row["expected"] == "unknown" and row["verdict"]["cause_correct"]
            for row in cohort
        )
        totals["counterfactuals_correct"] = sum(
            row["incident"].startswith("counterfactual-")
            and row["verdict"]["cause_correct"]
            for row in cohort
        )
        totals["followups"] = [
            {
                "incident": row["incident"],
                "tool": row["evidence_quality"]["followup_tool"],
                "initial_cause": row["evidence_quality"]["followup_initial_cause"],
                "final_cause": (row["diagnosis"] or {}).get("cause"),
                "expected_cause": row["expected"],
            }
            for row in cohort
            if row["evidence_quality"]["followup_tool"]
        ]
        totals["confidence"] = {}
        for row in cohort:
            quality = row["evidence_quality"]["diagnosis"]
            confidence = quality["confidence"] if quality else "no_diagnosis"
            count = totals["confidence"].setdefault(
                confidence, {"runs": 0, "correct": 0}
            )
            count["runs"] += 1
            count["correct"] += row["verdict"]["cause_correct"]
        totals["unsupported_explanation_matches"] = sum(
            not row["explanation_check"]["passed"]
            for row in cohort
            if row.get("explanation_check")
        )
        if policy != "selective-citations":
            continue
        totals["review_statuses"] = dict(
            Counter(row["citation_review"] or "no_initial_diagnosis" for row in cohort)
        )
        totals["review_calls"] = sum(
            any(event.get("phase") == "citation_review" for event in row["trace"])
            for row in cohort
        )
        totals["missed_weak_citations"] = sum(
            row["citation_review"] == "skipped"
            and row["original_verdict"]["cause_correct"]
            and not row["original_verdict"]["passed"]
            for row in cohort
        )
        totals["repairs"] = sum(
            not row["original_verdict"]["passed"] and row["verdict"]["passed"]
            for row in cohort
        )
        totals["lost_support"] = sum(
            row["original_verdict"]["passed"] and not row["verdict"]["passed"]
            for row in cohort
        )
        totals["unsupported_accepts"] = sum(
            row["citation_review"] == "accepted" and not row["verdict"]["passed"]
            for row in cohort
        )
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in (args.folder / "runs.jsonl").read_text().splitlines()
    ]
    manifest = json.loads((args.folder / "manifest.json").read_text())
    print(json.dumps(report(rows, manifest), indent=2))


if __name__ == "__main__":
    main()
