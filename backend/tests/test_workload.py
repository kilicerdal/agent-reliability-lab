import psycopg
import pytest
from lab.contracts import Diagnosis
from lab.db import connect
from lab.evaluator import evaluate
from lab.sandbox import SCENARIOS, fingerprint, reproduce
from lab.tools import dispatch


@pytest.mark.parametrize("kind", list(SCENARIOS))
def test_real_faults_and_independent_verdict(database, kind):
    e = reproduce(kind)
    before = fingerprint(e)
    trace = []
    for name in ["read_logs", "read_deployments", "read_queue", "read_health"]:
        trace.append({"type": "tool", "ok": True, "result": dispatch(name, {}, e)})
    records = trace[0]["result"]["records"]
    signals = {r["signal"] for r in records}
    assert set(SCENARIOS[kind]["required"]) <= signals
    d = Diagnosis(
        cause=SCENARIOS[kind]["cause"],
        explanation="Fixture diagnosis for an actual synthetic execution.",
        evidence_ids=[
            r["evidence_id"]
            for r in records
            if r["signal"] in SCENARIOS[kind]["required"]
        ],
        alternative="Other services can fail independently.",
        next_check="Compare the service configuration with the healthy control.",
    )
    assert evaluate(kind, d, trace, before, fingerprint(e))["passed"]
    with connect() as c:
        status = c.execute(
            "SELECT status FROM orders WHERE experiment=%s", (e,)
        ).fetchone()["status"]
    assert status == (
        "queued" if kind in ["worker-failure", "dependency-failure"] else "completed"
    )


def test_reader_cannot_read_fault_configuration_or_write(database):
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        connect(readonly=True) as c,
    ):
        c.execute("SELECT * FROM experiments")
    with (
        pytest.raises(
            (
                psycopg.errors.InsufficientPrivilege,
                psycopg.errors.ReadOnlySqlTransaction,
            )
        ),
        connect(readonly=True) as c,
    ):
        c.execute("DELETE FROM orders")


def test_tools_bound_to_current_experiment(database):
    a = reproduce("healthy")
    b = reproduce("worker-failure")
    ar = dispatch("read_logs", {}, a)["records"]
    br = dispatch("read_logs", {}, b)["records"]
    assert not {r["evidence_id"] for r in ar} & {r["evidence_id"] for r in br}
    for name, args in [
        ("execute_sql", {}),
        ("read_logs", {"experiment": b}),
        ("restart_worker", {}),
    ]:
        with pytest.raises(ValueError):
            dispatch(name, args, a)
