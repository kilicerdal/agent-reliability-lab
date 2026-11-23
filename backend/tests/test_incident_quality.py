import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.reliability import recovery_benchmark as benchmark
from backend.reliability.agent import investigate
from backend.reliability.assurance import (
    CitationReview,
    ClaimCitation,
    SupportedDiagnosis,
)
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


@pytest.mark.parametrize(
    ("incident_id", "expected_trigger"),
    [
        ("overlapping-faults", "conflicting_current_signals"),
        ("counterfactual-confirmed", None),
    ],
)
def test_selective_review_routes_scoped_conflicts(
    suite, monkeypatch, incident_id, expected_trigger
):
    cases, key = suite
    case, answer = cases[incident_id], key[incident_id]
    recorded = json.loads((FIXTURES / "selective-routing.json").read_text())
    row = next(
        row
        for row in recorded
        if row["incident"] == incident_id
        and row["model"] == "gpt-6-luna"
        and row["prompt"] == "selective-citations"
    )
    calls = []

    def replay(_alert, _dispatch, _client, _budget, **options):
        calls.append(options)
        if len(calls) == 1:
            options["trace"].extend(
                event
                for event in row["trace"]
                if event.get("phase") != "citation_review"
            )
            return SupportedDiagnosis.model_validate(row["original_diagnosis"]), [], {}
        return CitationReview(claims=[]), [], {}

    monkeypatch.setattr(benchmark, "investigate", replay)
    monkeypatch.setattr(benchmark, "Budget", lambda **_: object())
    result = benchmark.run_once(
        None,
        row["model"],
        row["prompt"],
        case.alert,
        incident_dispatch(case),
        answer.cause,
        answer.judgments,
        incident=case,
    )
    if expected_trigger:
        assert row["citation_review"] == "skipped"
        assert not row["original_verdict"]["passed"]
        assert expected_trigger in result["review_triggers"]
        assert len(calls) == 2
    else:
        assert result["citation_review"] == "skipped"
        assert len(calls) == 1
    assert result["verdict"]["cause_correct"]


@pytest.mark.parametrize(
    ("incident_id", "initial_correct"),
    [("counterfactual-confirmed", False), ("counterfactual-unresolved", True)],
)
def test_targeted_read_scores_same_initial_diagnosis(
    suite, monkeypatch, incident_id, initial_correct
):
    cases, key = suite
    case, answer = cases[incident_id], key[incident_id]
    initial = SupportedDiagnosis(
        cause="unknown",
        explanation="The effective configuration is not yet established.",
        alternative="The parcel worker could be stopped.",
        next_check="Read the current deployment settings.",
        evidence_ids=["n-5"],
        claims=[
            ClaimCitation(
                kind=kind, evidence_id="n-5", quote=case.tools["read_logs"][0].detail
            )
            for kind in ("mechanism", "configuration")
        ],
    )
    final = initial.model_copy(
        update={
            "cause": answer.cause,
            "evidence_ids": ["n-5", "n-3"],
            "claims": [
                ClaimCitation(
                    kind=rule.kind,
                    evidence_id=rule.evidence_id,
                    quote=rule.required_excerpt,
                )
                for rule in answer.judgments
                if rule.verdict == "supports"
            ],
        }
    )

    def tool_call(name):
        return SimpleNamespace(
            type="function_call",
            name=name,
            arguments="{}",
            call_id=name,
            model_dump=lambda **_: {"type": "function_call", "call_id": name},
        )

    responses = iter(
        [
            ([tool_call("read_logs")], None),
            ([], initial),
            ([tool_call("read_deployments")], None),
            ([], final),
        ]
    )
    payloads = []

    def create(**payload):
        payloads.append(payload)
        output, diagnosis = next(responses)
        return SimpleNamespace(
            output=output,
            output_text=diagnosis.model_dump_json() if diagnosis else "",
            id="mock",
            model="fixture",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    monkeypatch.setattr(
        benchmark,
        "Budget",
        lambda **_: SimpleNamespace(reserve=lambda: "mock", settle=lambda *_: 0),
    )
    result = benchmark.run_once(
        SimpleNamespace(responses=SimpleNamespace(create=create)),
        "gpt-6-luna",
        "check-support",
        case.alert,
        incident_dispatch(case),
        answer.cause,
        answer.judgments,
        incident=case,
    )
    quality = result["evidence_quality"]
    comparison = quality["followup_comparison"]
    assert quality["followup_initial_cause"] == "unknown"
    assert quality["followup_tool"] == "read_deployments"
    assert comparison["read_observed"]
    assert comparison["before"]["cause_correct"] is initial_correct
    assert not comparison["before"]["passed"]
    assert comparison["final_cause"] == answer.cause
    assert comparison["after"]["passed"]
    assert result["verdict"] == comparison["after"]
    assert payloads[2]["tool_choice"] == {
        "type": "function",
        "name": "read_deployments",
    }
    assert len(payloads) == 4
