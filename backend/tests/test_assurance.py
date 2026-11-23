import json

import pytest

from backend.reliability.assurance import (
    ClaimCitation,
    EvidenceJudgment,
    SupportedDiagnosis,
    grade_claims,
)
from backend.reliability.blind_intake import dispatch_observations, load_suite
from backend.reliability.live_challenges import LiveChallenge

WORKLOAD = "PostgreSQL waited 900 ms while inventory remained healthy."
CONFIG = "The active lookup path adds a configured SQL delay."
STALE = "A corrected dashboard note now rules out a database delay."


def diagnosis():
    return SupportedDiagnosis(
        cause="db_latency",
        explanation="The order lookup spends its time inside the database.",
        evidence_ids=["obs-1", "obs-2"],
        alternative="The external inventory service could contribute.",
        next_check="Compare additional lookup spans for consistency.",
        claims=[
            ClaimCitation(kind="mechanism", evidence_id="obs-1", quote=WORKLOAD),
            ClaimCitation(kind="configuration", evidence_id="obs-2", quote=CONFIG),
        ],
    )


def test_citation_support_rejects_observed_but_inadequate_evidence():
    records = {"obs-1": WORKLOAD, "obs-2": CONFIG, "obs-3": STALE}
    trace = [
        {
            "type": "tool",
            "ok": True,
            "result": {
                "records": [
                    {"evidence_id": key, "detail": text}
                    for key, text in records.items()
                ]
            },
        },
    ]
    rubric = [
        EvidenceJudgment(
            kind="mechanism",
            evidence_id="obs-1",
            verdict="supports",
            required_excerpt="PostgreSQL waited 900 ms",
        ),
        EvidenceJudgment(kind="configuration", evidence_id="obs-2", verdict="supports"),
        EvidenceJudgment(kind="mechanism", evidence_id="obs-2", verdict="irrelevant"),
        EvidenceJudgment(kind="mechanism", evidence_id="obs-3", verdict="contradicts"),
    ]
    result = diagnosis()
    assert grade_claims(result, "db_latency", trace, rubric)["passed"]
    result.evidence_ids.append("obs-3")
    for citation, quote, verdict in [
        ("obs-2", CONFIG, "irrelevant"),
        ("obs-3", STALE, "contradicts"),
        ("obs-1", "There was a 2000 ms delay.", "quotation_mismatch"),
        ("obs-1", "inventory remained healthy", "omits_supporting_excerpt"),
        ("obs-9", WORKLOAD, "unobserved"),
    ]:
        result.claims[0] = ClaimCitation(
            kind="mechanism", evidence_id=citation, quote=quote
        )
        report = grade_claims(result, "db_latency", trace, rubric)
        assert report["cause_correct"] and not report["passed"]
        assert report["claims"][0]["verdict"] == verdict


def test_blind_intake_separates_payload_from_answer_key(tmp_path):
    observations = tmp_path / "observations.json"
    key = tmp_path / "key.json"
    observations.write_text(
        json.dumps(
            [
                {
                    "id": "case-a",
                    "alert": "Order lookup stalls.",
                    "tools": {
                        "read_logs": [
                            {"evidence_id": "obs-1", "detail": WORKLOAD},
                            {"evidence_id": "obs-2", "detail": CONFIG},
                        ]
                    },
                }
            ]
        )
    )
    answer = {
        "id": "case-a",
        "cause": "db_latency",
        "reviewer": "fixture-reviewer",
        "judgments": [
            {
                "kind": "mechanism",
                "evidence_id": "obs-1",
                "verdict": "supports",
                "required_excerpt": "PostgreSQL waited 900 ms",
            },
            {
                "kind": "configuration",
                "evidence_id": "obs-2",
                "verdict": "supports",
                "required_excerpt": "adds a configured SQL delay",
            },
        ],
    }
    key.write_text(json.dumps([answer]))
    cases, answers, manifest = load_suite(observations, key)
    assert manifest["cases"] == 1
    assert answers["case-a"].cause == "db_latency"
    data = dispatch_observations(cases[0], "read_logs", {})
    payload = json.dumps(data)
    assert all(
        secret not in payload
        for secret in ("db_latency", "fixture-reviewer", "supports", "case-a")
    )
    assert payload.count("evidence_id") == 2
    answer["judgments"][0]["evidence_id"] = "obs-9"
    key.write_text(json.dumps([answer]))
    with pytest.raises(ValueError, match="invalid answer"):
        load_suite(observations, key)


@pytest.mark.parametrize(
    ("scenario", "event"),
    [
        ("http-timeout", "http_read_timeout"),
        ("sql-timeout", "postgres_statement_timeout"),
    ],
)
def test_real_tool_timeout_then_success(database, scenario, event):
    challenge = LiveChallenge(scenario)
    read, events = challenge.tools()
    assert read("read_logs", {}) == {"error": "timeout", "retryable": True}
    assert events == [event]
    assert read("read_logs", {})["records"]
    assert events == [event]


def test_live_telemetry_loss_and_conflict(database):
    loss = LiveChallenge("telemetry-loss")
    read, _ = loss.tools()
    assert {r["signal"] for r in read("read_logs", {})["records"]} == {
        "telemetry_gap",
        "configuration_gap",
    }
    conflict = LiveChallenge("stale-conflict")
    read, _ = conflict.tools()
    assert {"stale_summary", "worker_offline"} <= {
        r["signal"] for r in read("read_logs", {})["records"]
    }
