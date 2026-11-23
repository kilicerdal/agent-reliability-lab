"""Verify structured claim citations against an independent evidence rubric."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.lab.contracts import Diagnosis

ClaimKind = Literal["mechanism", "configuration"]


class ClaimCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ClaimKind
    evidence_id: str
    quote: str = Field(min_length=8, max_length=1000)


class SupportedDiagnosis(Diagnosis):
    claims: list[ClaimCitation] = Field(min_length=2, max_length=4)


class CitationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimCitation] = Field(max_length=2)


class EvidenceJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ClaimKind
    evidence_id: str
    verdict: Literal["supports", "contradicts", "irrelevant"]
    required_excerpt: str | None = Field(default=None, min_length=8)


def observed_records(trace):
    observed = {}
    inconsistent = set()
    for event in trace:
        if event["type"] != "tool" or not event.get("ok"):
            continue
        for record in event["result"].get("records", []):
            evidence_id = record["evidence_id"]
            detail = record["detail"]
            if evidence_id in observed and observed[evidence_id] != detail:
                inconsistent.add(evidence_id)
            observed[evidence_id] = detail
    return observed, inconsistent


def apply_citation_review(diagnosis, review, records):
    if {claim.kind for claim in review.claims} != {"mechanism", "configuration"}:
        return None
    if any(
        claim.quote not in records.get(claim.evidence_id, "") for claim in review.claims
    ):
        return None
    return diagnosis.model_copy(
        update={
            "claims": review.claims,
            "evidence_ids": list(
                dict.fromkeys(claim.evidence_id for claim in review.claims)
            ),
        }
    )


def grade_claims(diagnosis, expected_cause, trace, rubric):
    """Judge exact quotations and independently labeled support, one claim at a time."""
    if diagnosis is None:
        return {"cause_correct": False, "passed": False, "claims": []}

    observed, inconsistent = observed_records(trace)
    citations = set(diagnosis.evidence_ids)
    reviewed = {(row.kind, row.evidence_id): row for row in rubric}
    claims = []
    for claim in diagnosis.claims:
        detail = observed.get(claim.evidence_id)
        if detail is None or claim.evidence_id not in citations:
            verdict = "unobserved"
        elif claim.evidence_id in inconsistent:
            verdict = "inconsistent_record"
        elif claim.quote not in detail:
            verdict = "quotation_mismatch"
        else:
            judgment = reviewed.get((claim.kind, claim.evidence_id))
            if judgment is None:
                verdict = "unreviewed"
            elif (
                judgment.required_excerpt
                and judgment.required_excerpt not in claim.quote
            ):
                verdict = "omits_supporting_excerpt"
            else:
                verdict = judgment.verdict
        claims.append({**claim.model_dump(), "verdict": verdict})
    cause_correct = diagnosis.cause == expected_cause
    return {
        "cause_correct": cause_correct,
        "passed": cause_correct
        and set(observed) >= citations
        and all(item["verdict"] == "supports" for item in claims)
        and {item["kind"] for item in claims} == {"mechanism", "configuration"}
        and not any(event["type"] == "tool" and not event.get("ok") for event in trace),
        "claims": claims,
    }
