import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.reliability import recovery_benchmark as benchmark
from backend.reliability.agent import investigate
from backend.reliability.assurance import ClaimCitation, SupportedDiagnosis
from backend.reliability.blind_intake import incident_dispatch, load_suite
from backend.reliability.incident_quality import (
    check_explanation,
    current_records,
    evidence_decision,
)

FIXTURES = Path(__file__).resolve().parents[1] / "reliability" / "quality-fixtures"


@pytest.fixture
def suite():
    cases, key, _ = load_suite(
        FIXTURES / "observations.json", FIXTURES / "answers.json"
    )
    return {case.id: case for case in cases}, key


def test_counterfactual_and_multi_fault_baseline(suite):
    cases, key = suite
    confirmed = cases["counterfactual-confirmed"]
    unresolved = cases["counterfactual-unresolved"]
    assert confirmed.alert == unresolved.alert
    assert confirmed.tools["read_logs"] == unresolved.tools["read_logs"]
    assert (
        confirmed.tools["read_deployments"][1:]
        == unresolved.tools["read_deployments"][1:]
    )
    for case in cases.values():
        assert evidence_decision(case)["cause"] == key[case.id].cause
    assert set(evidence_decision(cases["overlapping-faults"])["matched_rules"]) == {
        "db_latency",
        "worker_stopped",
    }
    assert "n-9" not in current_records(confirmed)


@pytest.mark.parametrize(
    ("name", "tool", "first"),
    [
        ("timeout-healthy", "read_logs", {"error": "timeout", "retryable": True}),
        ("malformed-fallback", "read_logs", {"error": "malformed", "retryable": False}),
        (
            "compound-deploy-feed",
            "read_deployments",
            {"error": "unavailable", "retryable": False},
        ),
        ("empty-with-stale-worker", "read_logs", {"records": []}),
    ],
)
def test_fault_dispatch(suite, name, tool, first):
    cases, _ = suite
    dispatch = incident_dispatch(cases[name])
    assert dispatch(tool, {}) == first
    if first.get("retryable"):
        assert dispatch(tool, {})["records"]
        assert incident_dispatch(cases[name])(tool, {}) == first
    else:
        assert dispatch(tool, {}) == first


def test_partial_dispatch_and_scoped_handoff(suite):
    cases, _ = suite
    partial = incident_dispatch(cases["partial-lock"])("read_logs", {})
    assert partial["partial"] and len(partial["records"]) == 1
    case = cases["counterfactual-confirmed"]
    mechanism = case.tools["read_logs"][0]
    configuration = case.tools["read_deployments"][0]
    diagnosis = SupportedDiagnosis(
        cause="worker_stopped",
        explanation="The worker restarted at 09:33.",
        evidence_ids=[mechanism.evidence_id, configuration.evidence_id],
        alternative="The upstream could be unavailable.",
        next_check="Read deployments.",
        claims=[
            ClaimCitation(
                kind=kind, evidence_id=record.evidence_id, quote=record.detail
            )
            for kind, record in (
                ("mechanism", mechanism),
                ("configuration", configuration),
            )
        ],
    )
    dispatch = incident_dispatch(case)
    trace = [{"type": "tool", "ok": True, "result": dispatch("read_logs", {})}]
    first = evidence_decision(case, diagnosis, records=current_records(case, trace))
    assert first["confidence"] == "plausible"
    assert first["handoff"]["next_tool"] == "read_deployments"
    trace.append(
        {"type": "tool", "ok": True, "result": dispatch("read_deployments", {})}
    )
    assert (
        evidence_decision(case, diagnosis, records=current_records(case, trace))[
            "confidence"
        ]
        == "confirmed"
    )
    assert not check_explanation(diagnosis, ["the worker restarted at 09:33"])["passed"]


def test_investigation_requests_one_targeted_read():
    from backend.lab.contracts import Diagnosis

    diagnosis = Diagnosis(
        cause="unknown",
        explanation="The effective setting is missing.",
        evidence_ids=["obs-1"],
        alternative="Worker failure is possible.",
        next_check="Read deployment settings.",
    )
    call = SimpleNamespace(
        type="function_call",
        name="read_deployments",
        arguments="{}",
        call_id="read-1",
        model_dump=lambda **_: {"type": "function_call", "call_id": "read-1"},
    )
    responses = iter([[], [call], []])
    payloads = []

    def create(**payload):
        payloads.append(payload)
        return SimpleNamespace(
            output=next(responses),
            output_text=diagnosis.model_dump_json(),
            id="mock",
            model="fixture",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    investigate(
        "Alert",
        lambda name, _: {"records": []},
        SimpleNamespace(responses=SimpleNamespace(create=create)),
        SimpleNamespace(reserve=lambda: "mock", settle=lambda *_: 0),
        improved=True,
        trace=[],
        max_requests=3,
        model="fixture",
        followup=lambda *_: "read_deployments",
    )
    assert payloads[1]["tool_choice"] == {
        "type": "function",
        "name": "read_deployments",
    }
    assert "tool_choice" not in payloads[0] and "tool_choice" not in payloads[2]


def test_sealed_resume_skips_completed_and_blocks_uncertain_trials(
    tmp_path, suite, monkeypatch
):
    cases, key = suite
    name = "timeout-healthy"
    selected = [(cases[name], key[name])]
    calls = []

    def fake_run(_client, model, prompt, *_args, **_kwargs):
        calls.append(model)
        return {
            "prompt": prompt,
            "model": model,
            "verdict": {"passed": True},
            "diagnosis": None,
            "error": None,
        }

    monkeypatch.setattr(benchmark, "run_once", fake_run)
    initial = benchmark.run_suite(None, tmp_path, selected, 1, live=False, paired=True)
    assert len(calls) == 2
    assert (
        benchmark.run_suite(
            None, tmp_path, selected, 1, live=False, paired=True, resume=True
        )
        == initial
    )
    assert len(calls) == 2
    log = tmp_path / "runs.jsonl"
    log.write_text(json.dumps(initial[0]) + "\n")
    pending = tmp_path / "in-flight.json"
    pending.write_text(json.dumps([name, 1, initial[1]["model"], initial[1]["prompt"]]))
    with pytest.raises(ValueError, match="uncertain API usage"):
        benchmark.run_suite(
            None, tmp_path, selected, 1, live=False, paired=True, resume=True
        )
    assert len(calls) == 2
    pending.unlink()
    assert (
        len(
            benchmark.run_suite(
                None, tmp_path, selected, 1, live=False, paired=True, resume=True
            )
        )
        == 2
    )
    assert calls[-1] == initial[1]["model"]
