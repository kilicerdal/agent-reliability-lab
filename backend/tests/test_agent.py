import json
from types import SimpleNamespace

import pytest
from lab import agent
from lab.budget import Budget

from backend.lab import run as live_runner
from backend.reliability.agent import CAUSE_GUIDE
from backend.reliability.agent import investigate as investigate_reliability


class Item:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_dump(self, **kwargs):
        return self.__dict__


class Responses:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.payloads = []

    def create(self, **payload):
        self.payloads.append(payload)
        return next(self.outputs)


def response(items, text=""):
    return SimpleNamespace(
        id="fixture-response",
        model=agent.MODEL,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        output=items,
        output_text=text,
    )


def answer():
    return json.dumps(
        {
            "cause": "unknown",
            "explanation": "Insufficient observations to establish a cause.",
            "evidence_ids": ["obs-1"],
            "alternative": "Several services may explain this alert.",
            "next_check": "Collect another independent workload observation.",
        }
    )


def tool(name="read_logs"):
    return Item(type="function_call", name=name, arguments="{}", call_id="fixture-call")


def test_tool_loop_uses_scoped_dispatch_and_returns_structured_answer(
    tmp_path, monkeypatch
):
    calls = []

    def dispatch(name, args, e):
        calls.append((name, args, e))
        return {"records": [{"evidence_id": "obs-1", "detail": "Fixture signal"}]}

    monkeypatch.setattr(agent, "dispatch", dispatch)
    r = Responses([response([tool()]), response([], answer())])
    budget = Budget(tmp_path / "budget.db")
    d, t, u = agent.investigate(
        "bound-experiment",
        "Investigate this alert",
        SimpleNamespace(responses=r),
        budget,
    )
    assert calls == [("read_logs", {}, "bound-experiment")]
    assert d.cause == "unknown" and len(t) == 3 and u["estimated_usd"] > 0
    assert "expected_cause" not in json.dumps(r.payloads)
    assert budget.summary()["unsettled_requests"] == 0


def test_provider_failure_retains_reservation_without_retry(tmp_path):
    class Broken:
        calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise TimeoutError("Fixture timeout")

    broken = Broken()
    b = Budget(tmp_path / "budget.db")
    with pytest.raises(TimeoutError):
        agent.investigate("e", "Alert", SimpleNamespace(responses=broken), b)
    assert broken.calls == 1 and b.summary()["unsettled_requests"] == 1


def test_step_limit_stops_repeated_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "dispatch", lambda *args: {"records": []})
    r = Responses([response([tool()]) for _ in range(9)])
    with pytest.raises(RuntimeError, match="step limit"):
        agent.investigate(
            "e", "Alert", SimpleNamespace(responses=r), Budget(tmp_path / "b.db")
        )
    assert len(r.payloads) == 8


def test_cause_contract_describes_each_enum_without_changing_validation(tmp_path):
    requests = []
    for use_contract in (False, True):
        provider = Responses([response([], answer())])
        diagnosis, _, _ = investigate_reliability(
            "Investigate this alert",
            lambda *_: pytest.fail("No tool was requested"),
            SimpleNamespace(responses=provider),
            Budget(tmp_path / "budget.db"),
            improved=True,
            trace=[],
            cause_contract=use_contract,
        )
        assert diagnosis.cause == "unknown"
        requests.append(provider.payloads[0])
    original, candidate = requests
    original_cause = original["text"]["format"]["schema"]["properties"]["cause"]
    candidate_cause = candidate["text"]["format"]["schema"]["properties"]["cause"]
    assert "description" not in original_cause
    description = candidate_cause.pop("description")
    assert candidate_cause == original_cause
    assert set(original_cause["enum"]) == CAUSE_GUIDE.keys()
    for label, definition in CAUSE_GUIDE.items():
        assert f"{label}: {definition}" in description
    assert "causal subsystem" in candidate["instructions"]
    assert "expected_cause" not in json.dumps(requests)


def test_live_runner_defaults_to_cause_contract_and_keeps_archived_captures_separate(
    tmp_path, monkeypatch
):
    fixture = json.loads(answer())
    fixture["cause"] = "db_latency"
    fixture["evidence_ids"] = ["obs-1", "obs-2"]
    provider = Responses([response([tool()]), response([], json.dumps(fixture))])
    calls = []

    def dispatch(name, args, experiment):
        calls.append((name, args, experiment))
        return {
            "records": [
                {"evidence_id": "obs-1", "signal": "query_slow"},
                {"evidence_id": "obs-2", "signal": "query_config_changed"},
            ]
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LAB_RESULTS_DIR", raising=False)
    monkeypatch.setenv("LAB_BUDGET_FILE", str(tmp_path / "test-budget.sqlite"))
    monkeypatch.setattr(live_runner, "init_db", lambda: None)
    monkeypatch.setattr(live_runner, "reproduce", lambda _: "sql-experiment")
    monkeypatch.setattr(live_runner, "fingerprint", lambda _: "unchanged")
    monkeypatch.setattr(live_runner, "dispatch", dispatch)
    monkeypatch.setattr(
        live_runner, "OpenAI", lambda **_: SimpleNamespace(responses=provider)
    )
    result = live_runner.run("database-slowdown")

    assert calls == [("read_logs", {}, "sql-experiment")]
    assert result["verdict"]["passed"]
    assert result["investigator_contract"] == "cause-contract"
    assert (
        "db_latency:"
        in provider.payloads[0]["text"]["format"]["schema"]["properties"]["cause"][
            "description"
        ]
    )
    assert "retryable timeout" in provider.payloads[0]["instructions"]
    assert (
        json.loads(
            (tmp_path / ".private/live-runs" / f"{result['id']}.json").read_text()
        )
        == result
    )
    assert not (tmp_path / "evidence").exists()
