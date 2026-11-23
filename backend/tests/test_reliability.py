import json

import pytest

from backend.lab.contracts import Diagnosis
from backend.reliability.evaluate import FIXTURES, IncidentTools, grade

CASES = json.loads(FIXTURES.read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_fixture_paths_and_strict_grading(case):
    tools = IncidentTools(case)
    trace = []

    def read(name):
        result = tools(name, {})
        trace.append({"type": "tool", "name": name, "ok": True, "result": result})
        return result

    affected = case["tool"]
    first = read(affected)
    if case["failure"] == "timeout":
        assert first == {"error": "timeout", "retryable": True}
        assert read(affected)["records"]
        assert IncidentTools(case)(affected, {}) == first
    elif case["failure"] == "missing":
        assert first == read(affected) == {"status": "unavailable", "records": []}
    elif case["failure"] == "conflict":
        assert first["records"][0]["evidence_id"] == "obs-3"

    for name in ("read_health", "read_logs", "read_deployments"):
        read(name)
    diagnosis = Diagnosis(
        cause=case["cause"],
        explanation="Diagnosis fixture for deterministic grader checks.",
        evidence_ids=["obs-1", "obs-2"],
        alternative="Another service may be affected.",
        next_check="Corroborate with a direct probe.",
    )
    result = grade(case, diagnosis, trace)
    assert result["strict_pass"]
    assert result["recovered"] == (
        case["failure"] in {"timeout", "missing", "conflict"}
    )
    assert not grade(case, diagnosis, [])["strict_pass"]
    assert not grade(case, None, trace)["correct_cause"]
    invented = diagnosis.model_copy(
        update={"evidence_ids": ["obs-1", "obs-2", "obs-999"]}
    )
    assert not grade(case, invented, trace)["strict_pass"]
    trace.append({"type": "tool", "name": "write", "ok": False, "result": {}})
    assert not grade(case, diagnosis, trace)["strict_pass"]
    with pytest.raises(ValueError):
        tools("read_health", {"experiment": "other"})
