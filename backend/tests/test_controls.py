import anyio
import pytest

from backend.controls import approval
from backend.controls.evidence import capture, restart_outcome, state
from backend.controls.remediation_lab import run_scenario
from backend.controls.server import CATALOG, REQUEST
from backend.lab.db import connect
from backend.lab.sandbox import reproduce, tick


def test_catalog_has_only_scoped_tools():
    assert {tool.name for tool in CATALOG} == {
        "read_logs",
        "read_deployments",
        "read_health",
        "read_queue",
        REQUEST,
    }
    assert all(
        tool.input_schema["properties"] == {}
        and not tool.input_schema["additionalProperties"]
        for tool in CATALOG
    )


def test_mcp_scope_and_operator_approval(database):
    result = anyio.run(capture)
    assert all(result["checks"].values()), result["checks"]


@pytest.mark.parametrize("persistent_fault", [False, True])
def test_stateful_remediation_matrix(database, persistent_fault):
    approval.install()
    result = anyio.run(run_scenario, persistent_fault)
    assert all(result["checks"].values()), result["checks"]
    assert result["timeline"][1]["queue_observation"]["queued"] == 1
    assert result["outcome"]["workload_recovered"] is not persistent_fault


def test_approval_rolls_back_mid_execution_and_detects_persistent_incident(
    database, monkeypatch
):
    approval.install()
    experiment = reproduce("worker-failure")
    before = state(experiment)
    with approval.scoped_mcp_dsn(experiment) as dsn:
        monkeypatch.setenv("LAB_READER_DSN", dsn)
        assert (
            approval.request_restart(experiment)["status"] == "pending_operator_review"
        )
    real_record = approval.record

    def interrupt(*args):
        raise RuntimeError("Interrupted before audit event")

    monkeypatch.setattr(approval, "record", interrupt)
    with pytest.raises(RuntimeError, match="Interrupted"):
        approval.approve_restart(experiment)
    assert state(experiment) == before
    monkeypatch.setattr(approval, "record", real_record)
    assert approval.approve_restart(experiment) == "applied"
    assert approval.approve_restart(experiment) == "already_applied"
    with connect() as conn:
        conn.execute(
            "UPDATE experiments SET inventory_mode='wrong-region' WHERE id=%s",
            (experiment,),
        )
    tick(experiment)
    assert restart_outcome(before, state(experiment)) == {
        "action_applied": True,
        "workload_recovered": False,
        "order_status": "queued",
    }
    with connect() as conn:
        conn.execute(
            "UPDATE experiments SET inventory_mode='healthy' WHERE id=%s", (experiment,)
        )
    tick(experiment)
    tick(experiment)
    assert restart_outcome(before, state(experiment))["workload_recovered"]
    assert (
        state(experiment)["restart_events"]
        == state(experiment)["completion_events"]
        == 1
    )
