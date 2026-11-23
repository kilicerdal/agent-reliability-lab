import pytest

from backend.reliability.agent import CAUSE_GUIDE
from backend.reliability.citation_promotion import POLICY, evaluate_promotion
from backend.reliability.recovery_benchmark import RATES


@pytest.fixture
def cohort():
    manifest = {"suite": {"cases": 20, "answer_key_sha256": "fixture"}}
    attestation = {
        "reviewer": "external-reviewer",
        "independently_authored": True,
        "graded_before_model_output": True,
        "policy": POLICY,
        "suite": manifest["suite"],
    }
    rows = [
        {
            "model": model,
            "incident": f"{cause}-{index}",
            "expected": cause,
            "original_verdict": {
                "cause_correct": True,
                "passed": index != 0,
                "claims": [{"verdict": "supports" if index else "irrelevant"}],
            },
            "verdict": {"cause_correct": True, "passed": True},
            "elapsed_ms": 2000,
            "initial_elapsed_ms": 1000,
            "trace": [{"estimated_usd": 0.001, "phase": "citation_review"}],
            "review_triggers": [],
            "error": None,
        }
        for model in RATES
        for cause in CAUSE_GUIDE
        for index in range(4)
    ]
    return manifest, rows, attestation


def test_gate_allows_manual_promotion_when_every_model_meets_policy(cohort):
    manifest, rows, attestation = cohort
    report = evaluate_promotion(manifest, rows, attestation)
    assert report["eligible_for_manual_promotion"]
    assert all(model["repairs"] == 5 for model in report["models"].values())


@pytest.mark.parametrize(
    ("change", "failed_check"),
    [
        ("cause", "cause_accuracy_preserved"),
        ("support", "lost_support_within_limit"),
        ("latency", "p95_latency_within_limit"),
        ("cost", "added_cost_within_limit"),
        ("error", "no_review_execution_errors"),
    ],
)
def test_gate_blocks_regressions(cohort, change, failed_check):
    manifest, rows, attestation = cohort
    model = rows[0]["model"]
    for row in rows:
        if row["model"] != model:
            continue
        if change == "cause":
            row["verdict"]["cause_correct"] = False
        elif change == "support":
            row["verdict"]["passed"] = False
        elif change == "latency":
            row["elapsed_ms"] = 5000
        elif change == "cost":
            row["trace"][0]["estimated_usd"] = 0.01
        elif change == "error":
            row["error"] = "TimeoutError"
    report = evaluate_promotion(manifest, rows, attestation)
    assert not report["eligible_for_manual_promotion"]
    assert not report["models"][model]["checks"][failed_check]


def test_gate_rejects_attestation_for_a_different_seal(cohort):
    manifest, rows, attestation = cohort
    attestation["suite"] = {"cases": 20, "answer_key_sha256": "different"}
    report = evaluate_promotion(manifest, rows, attestation)
    assert not report["eligible_for_manual_promotion"]
    assert not report["cohort_checks"]["independent_attestation"]


def test_repeats_do_not_supply_missing_weak_incidents(cohort):
    manifest, rows, attestation = cohort
    for row in rows:
        if row["expected"] == "worker_stopped":
            row["original_verdict"]["passed"] = True
    report = evaluate_promotion(manifest, rows * 2, attestation)
    assert not report["eligible_for_manual_promotion"]
    assert all(
        model["distinct_weak_incidents"] == 4 for model in report["models"].values()
    )
