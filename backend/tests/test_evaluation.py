import pytest
from lab.contracts import Diagnosis
from lab.evaluator import evaluate
from lab.sandbox import SCENARIOS


def diagnosis(cause, ids):
    return Diagnosis(
        cause=cause,
        explanation="Measured evidence supports this cause.",
        evidence_ids=ids,
        alternative="A competing service failure remains possible.",
        next_check="Verify configuration against the last healthy capture.",
    )


def fixture(kind):
    records = [
        {"evidence_id": f"obs-{i}", "signal": signal}
        for i, signal in enumerate(SCENARIOS[kind]["required"])
    ]
    trace = [{"type": "tool", "ok": True, "result": {"records": records}}]
    return diagnosis(
        SCENARIOS[kind]["cause"], [r["evidence_id"] for r in records]
    ), trace


@pytest.mark.parametrize("kind", list(SCENARIOS))
def test_correct_diagnoses_with_observed_required_signals(kind):
    d, t = fixture(kind)
    assert evaluate(kind, d, t, "same", "same")["passed"]


@pytest.mark.parametrize(
    "change",
    ["wrong-cause", "invented-citation", "missing-signal", "mutation", "denied"],
)
def test_oracle_rejects_plausible_but_invalid_results(change):
    d, t = fixture("worker-failure")
    after = "same"
    if change == "wrong-cause":
        d.cause = "db_latency"
    if change == "invented-citation":
        d.evidence_ids.append("obs-999999")
    if change == "missing-signal":
        d.evidence_ids = d.evidence_ids[:1]
    if change == "mutation":
        after = "changed"
    if change == "denied":
        t.append({"type": "tool", "ok": False})
    assert not evaluate("worker-failure", d, t, "same", after)["passed"]
