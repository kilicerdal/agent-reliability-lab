from copy import deepcopy

import pytest

from backend.reliability.benchmark import compare


@pytest.fixture
def capture():
    manifest = {
        "suite": {
            "observations_sha256": "observations",
            "answer_key_sha256": "answers",
            "protocol_sha256": "old",
        }
    }
    row = {
        "model": "gpt-6-luna",
        "incident": "one",
        "repeat": 1,
        "expected": "worker_stopped",
        "diagnosis": {"cause": "worker_stopped"},
        "verdict": {"cause_correct": True, "passed": True},
        "elapsed_ms": 1000,
        "estimated_usd": 0.002,
    }
    return manifest, [row]


def test_comparison_reports_per_trial_changes(capture):
    candidate = deepcopy(capture)
    candidate[0]["suite"]["protocol_sha256"] = "new"
    row = candidate[1][0]
    row.update(
        diagnosis={"cause": "unknown"},
        verdict={"cause_correct": False, "passed": False},
        elapsed_ms=1300,
        estimated_usd=0.0025,
    )
    result = compare(capture, candidate)
    assert not result["same_protocol"]
    assert not result["no_cause_or_support_regressions"]
    assert (
        result["counts"]["support_lost"] == result["counts"]["cause_regressions"] == 1
    )
    assert result["trials"][0]["elapsed_ms_delta"] == 300
    assert result["trials"][0]["estimated_usd_delta"] == 0.0005


@pytest.mark.parametrize("reason", ["seal", "coverage", "duplicate"])
def test_comparison_blocks_unmatched_trials(capture, reason):
    candidate = deepcopy(capture)
    if reason == "seal":
        candidate[0]["suite"]["answer_key_sha256"] = "changed"
    elif reason == "coverage":
        candidate[1][0]["repeat"] = 2
    else:
        candidate[1].append(candidate[1][0])
    with pytest.raises(ValueError):
        compare(capture, candidate)
