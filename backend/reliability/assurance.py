"""Verify structured claim citations against an independent evidence rubric."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.lab.contracts import Diagnosis

ClaimKind = Literal["mechanism", "configuration"]
CLAIM_KINDS = {"mechanism", "configuration"}


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


def check_citations(diagnosis, observed, inconsistent):
    """Check citation structure against observed records without a grading key."""
    citations = set(diagnosis.evidence_ids)
    claim_errors = []
    for claim in diagnosis.claims:
        detail = observed.get(claim.evidence_id)
        error = None
        if detail is None or claim.evidence_id not in citations:
            error = "unobserved"
        elif claim.evidence_id in inconsistent:
            error = "inconsistent_record"
        elif claim.quote not in detail:
            error = "quotation_mismatch"
        claim_errors.append(error)
    issues = {
        "claim_errors": claim_errors,
        "unobserved_ids": sorted(citations - observed.keys()),
        "inconsistent_ids": sorted(citations & inconsistent),
        "missing_roles": sorted(
            CLAIM_KINDS - {claim.kind for claim in diagnosis.claims}
        ),
    }
    return {**issues, "passed": not any(any(items) for items in issues.values())}


def apply_citation_review(diagnosis, review, records):
    revised = diagnosis.model_copy(
        update={
            "claims": review.claims,
            "evidence_ids": list(
                dict.fromkeys(claim.evidence_id for claim in review.claims)
            ),
        }
    )
    checks = check_citations(revised, records, set())
    return revised if checks["passed"] else None


def grade_claims(diagnosis, expected_cause, trace, rubric):
    """Judge exact quotations and independently labeled support, one claim at a time."""
    if diagnosis is None:
        return {"cause_correct": False, "passed": False, "claims": []}

    observed, inconsistent = observed_records(trace)
    checks = check_citations(diagnosis, observed, inconsistent)
    reviewed = {(row.kind, row.evidence_id): row for row in rubric}
    claims = []
    for claim, verdict in zip(diagnosis.claims, checks["claim_errors"], strict=True):
        if verdict is None:
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
        and checks["passed"]
        and all(item["verdict"] == "supports" for item in claims)
        and not any(event["type"] == "tool" and not event.get("ok") for event in trace),
        "claims": claims,
    }
