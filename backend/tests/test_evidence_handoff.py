import json

from backend.reliability import recovery_benchmark
from backend.reliability.assurance import (
    ClaimCitation,
    EvidenceJudgment,
    SupportedDiagnosis,
)
from backend.reliability.evidence_handoff import build_handoff


def test_handoff_shares_only_read_observations_and_provisional_diagnosis(monkeypatch):
    mechanism = "Current jobs did not start in the affected window."
    configuration = "The active worker pool is configured for zero replicas."
    diagnosis = SupportedDiagnosis(
        cause="worker_stopped",
        explanation="The worker was stopped during the incident.",
        alternative="The dependency could have failed.",
        next_check="Verify the active worker pool.",
        evidence_ids=["obs-a", "obs-b"],
        claims=[
            ClaimCitation(kind="mechanism", evidence_id="obs-a", quote=mechanism),
            ClaimCitation(
                kind="configuration", evidence_id="obs-b", quote=configuration
            ),
        ],
    )
    events = [
        {
            "type": "tool",
            "ok": True,
            "name": name,
            "result": {
                "records": [
                    {
                        "evidence_id": evidence_id,
                        "detail": detail,
                        "context": {
                            "timestamp": "2026-11-23T13:15:00Z",
                            "service": "worker",
                            "environment": "lab",
                            "source": name,
                        },
                    }
                ]
            },
        }
        for name, evidence_id, detail in [
            ("read_logs", "obs-a", mechanism),
            ("read_deployments", "obs-b", configuration),
        ]
    ]
    packet = build_handoff(
        {
            "diagnosis": diagnosis.model_dump(),
            "expected": "private-score",
            "rubric": ["private-rubric"],
            "trace": [
                *events,
                {"type": "model", "model": "luna", "estimated_usd": 1},
                {
                    "type": "tool",
                    "name": "read_health",
                    "ok": False,
                    "result": {"error": "denied"},
                },
            ],
        }
    )
    assert set(packet) == {"provisional_diagnosis", "observations"}
    assert len(packet["observations"]) == 2
    assert packet["observations"][0]["result"] == events[0]["result"]
    assert "private-" not in json.dumps(packet)

    def replay(alert, dispatch, client, budget, **options):
        assert "independently assess" in options["instructions"].lower()
        assert "private-" not in alert
        assert options["trace"] == packet["observations"]
        return diagnosis, [], {}

    monkeypatch.setattr(recovery_benchmark, "investigate", replay)
    monkeypatch.setattr(recovery_benchmark, "Budget", lambda **_: object())
    rubric = [
        EvidenceJudgment(
            kind=claim.kind, evidence_id=claim.evidence_id, verdict="supports"
        )
        for claim in diagnosis.claims
    ]
    row = recovery_benchmark.run_once(
        None,
        "gpt-6.2-sol",
        "check-support",
        "Alert",
        None,
        "worker_stopped",
        rubric,
        handoff=packet,
    )
    assert row["verdict"]["passed"]
    assert row["estimated_usd"] == 0
