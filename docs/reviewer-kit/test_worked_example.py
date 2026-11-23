from pathlib import Path

from backend.reliability.assurance import (
    ClaimCitation,
    SupportedDiagnosis,
    grade_claims,
)
from backend.reliability.blind_intake import dispatch_observations, load_suite


def test_reviewer_kit_example_grades_strong_and_weak_citations():
    kit = Path(__file__).resolve().parent
    cases, answers, manifest = load_suite(
        kit / "observations.template.json", kit / "answers.template.json"
    )
    assert manifest["cases"] == 1
    case = cases[0]
    answer = answers[case.id]
    trace = [
        {"type": "tool", "ok": True, "result": dispatch_observations(case, tool, {})}
        for tool in case.tools
    ]
    strong = SupportedDiagnosis(
        cause="worker_stopped",
        explanation="The parcel consumer stopped processing scans.",
        alternative="Another subsystem could delay parcel processing.",
        next_check="Check the rollout history for the replica count.",
        evidence_ids=["obs-4", "obs-8"],
        claims=[
            ClaimCitation(
                kind="mechanism",
                evidence_id="obs-4",
                quote="the parcel consumer emitted no heartbeats and started no jobs",
            ),
            ClaimCitation(
                kind="configuration",
                evidence_id="obs-8",
                quote="Effective parcel consumer replica count was zero",
            ),
        ],
    )
    assert grade_claims(strong, answer.cause, trace, answer.judgments)["passed"]
    for evidence_id, quote, expected in (
        ("obs-6", "The pending parcel queue grew from 12 to 300", "irrelevant"),
        ("obs-4", "Scan requests returned success.", "omits_supporting_excerpt"),
    ):
        weak = strong.model_copy(deep=True)
        weak.claims[0] = ClaimCitation(
            kind="mechanism", evidence_id=evidence_id, quote=quote
        )
        weak.evidence_ids[0] = evidence_id
        verdict = grade_claims(weak, answer.cause, trace, answer.judgments)
        assert verdict["cause_correct"] and not verdict["passed"]
        assert verdict["claims"][0]["verdict"] == expected
