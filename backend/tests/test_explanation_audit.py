import pytest

from backend.reliability.explanation_audit import Assertion, audit


def test_supported_citations_do_not_excuse_unsupported_explanation():
    trace = [
        {
            "type": "tool",
            "ok": True,
            "result": {
                "records": [
                    {
                        "evidence_id": "obs-1",
                        "detail": "Effective worker count was zero.",
                    },
                    {"evidence_id": "obs-2", "detail": "The order remained queued."},
                ]
            },
        }
    ]
    supported = Assertion(
        text="The worker count was zero.",
        kind="configuration",
        verdict="supports",
        evidence_id="obs-1",
        quote="worker count was zero",
    )
    false_recovery = Assertion(
        text="The restart recovered the workload.",
        kind="recovery",
        verdict="contradicts",
        evidence_id="obs-2",
        quote="order remained queued",
    )
    invented_time = Assertion(
        text="The restart occurred at 09:33.",
        kind="timestamp",
        verdict="insufficient",
    )
    explanation = " ".join(
        entry.text for entry in (supported, false_recovery, invented_time)
    )
    assert audit(supported.text, trace, [supported])["passed"]
    result = audit(explanation, trace, [supported, false_recovery, invented_time])
    assert not result["passed"]
    assert [row["verdict"] for row in result["assertions"]] == [
        "supports",
        "contradicts",
        "insufficient",
    ]
    assert audit(explanation, trace, [supported])["unreviewed_spans"] == [
        false_recovery.text + " " + invented_time.text
    ]
    invented_quote = supported.model_copy(update={"quote": "worker count was two"})
    assert (
        audit(supported.text, trace, [invented_quote])["assertions"][0]["verdict"]
        == "unverifiable_quote"
    )
    with pytest.raises(ValueError, match="verbatim"):
        audit(supported.text, trace, [false_recovery])
