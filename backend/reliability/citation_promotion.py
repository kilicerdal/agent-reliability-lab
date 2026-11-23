"""Evaluate the pre-registered citation review promotion criteria offline."""

import argparse
import json
from collections import Counter
from pathlib import Path

from .agent import CAUSE_GUIDE
from .recovery_benchmark import RATES, summarize_review_policies
from .verify_paired_citations import verify

MIN_CASES = 20
POLICY = "citation-review-v1"
MIN_CASES_PER_CAUSE = 3
MIN_WEAK_CASES = 5
MAX_LOST_SUPPORT_RATE = 0.05
MAX_P95_INCREASE_MS = 3000
MAX_COST_INCREASE_PER_TRIAL = 0.005


def evaluate_promotion(manifest, rows, attestation=None):
    suite = manifest["suite"]
    graders = {row["incident"]: row["expected"] for row in rows}
    causes = Counter(graders.values())
    signed_off = bool(
        isinstance(attestation, dict)
        and isinstance(attestation.get("reviewer"), str)
        and attestation["reviewer"].strip()
        and attestation.get("independently_authored") is True
        and attestation.get("graded_before_model_output") is True
        and attestation.get("policy") == POLICY
        and attestation.get("suite") == suite
    )
    cohort = {
        "independent_attestation": signed_off,
        "minimum_distinct_incidents": len(graders) >= MIN_CASES,
        "minimum_distinct_incidents_by_cause": all(
            causes[cause] >= MIN_CASES_PER_CAUSE for cause in CAUSE_GUIDE
        ),
        "required_models": {row["model"] for row in rows} == set(RATES),
    }
    summaries = summarize_review_policies(rows)
    models = {}
    for model in RATES:
        trials = [row for row in rows if row["model"] == model]
        if not trials:
            continue
        off = summaries[f"{model}/off"]
        always = summaries[f"{model}/always"]
        repairs = losses = initially_supported = 0
        weak = set()
        support_delta = Counter(dict.fromkeys(CAUSE_GUIDE, 0))
        for row in trials:
            before = row["original_verdict"]
            after = row["verdict"]
            initially_supported += before["passed"]
            if (
                before["cause_correct"]
                and not before["passed"]
                and any(claim["verdict"] != "supports" for claim in before["claims"])
            ):
                weak.add(row["incident"])
            repairs += not before["passed"] and after["passed"]
            losses += before["passed"] and not after["passed"]
            support_delta[row["expected"]] += int(after["passed"]) - int(
                before["passed"]
            )
        lost_rate = losses / initially_supported if initially_supported else None
        p95_delta = always["p95_ms"] - off["p95_ms"]
        cost_delta = round(
            (always["estimated_usd"] - off["estimated_usd"]) / len(trials), 9
        )
        checks = {
            "minimum_weak_incidents": len(weak) >= MIN_WEAK_CASES,
            "cause_accuracy_preserved": all(
                row["original_verdict"]["cause_correct"]
                == row["verdict"]["cause_correct"]
                for row in trials
            ),
            "more_repairs_than_losses": repairs > losses,
            "no_cause_support_regression": all(
                delta >= 0 for delta in support_delta.values()
            ),
            "lost_support_within_limit": lost_rate is not None
            and lost_rate <= MAX_LOST_SUPPORT_RATE,
            "no_review_execution_errors": all(row["error"] is None for row in trials),
            "p95_latency_within_limit": p95_delta <= MAX_P95_INCREASE_MS,
            "added_cost_within_limit": cost_delta <= MAX_COST_INCREASE_PER_TRIAL,
        }
        models[model] = {
            "checks": checks,
            "repairs": repairs,
            "lost_support": losses,
            "initially_supported": initially_supported,
            "distinct_weak_incidents": len(weak),
            "support_delta_by_cause": dict(support_delta),
            "p95_increase_ms": p95_delta,
            "estimated_cost_increase_per_trial_usd": cost_delta,
        }
    eligible = all(cohort.values()) and all(
        all(result["checks"].values()) for result in models.values()
    )
    return {
        "policy": POLICY,
        "eligible_for_manual_promotion": eligible,
        "cohort_checks": cohort,
        "models": models,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--attestation", type=Path)
    args = parser.parse_args()
    if not __debug__:
        parser.error(
            "Run without Python optimization so evidence verification stays enabled"
        )
    manifest, rows = verify(args.folder, announce=False)
    attestation = json.loads(args.attestation.read_text()) if args.attestation else None
    report = evaluate_promotion(manifest, rows, attestation)
    print(json.dumps(report, indent=2))
    return 0 if report["eligible_for_manual_promotion"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
