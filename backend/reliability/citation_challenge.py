"""Challenge the citation reviewer with controlled strong and weak diagnosis inputs."""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from backend.lab.budget import Budget

from .agent import investigate
from .assurance import (
    CitationReview,
    ClaimCitation,
    SupportedDiagnosis,
    apply_citation_review,
    grade_claims,
)
from .blind_intake import dispatch_observations, load_suite
from .recovery_benchmark import RATES, REVIEW_CITATIONS


def variants(case, answer):
    claims = []
    for kind in ("mechanism", "configuration"):
        judgment = next(
            item
            for item in answer.judgments
            if item.verdict == "supports" and item.kind == kind
        )
        claims.append(
            ClaimCitation(
                kind=kind,
                evidence_id=judgment.evidence_id,
                quote=judgment.required_excerpt,
            )
        )
    diagnosis = SupportedDiagnosis(
        cause=answer.cause,
        explanation="The proposed cause is held fixed during review.",
        alternative="An alternative subsystem may explain the symptom.",
        next_check="Verify the effective settings in the incident window.",
        evidence_ids=[claim.evidence_id for claim in claims],
        claims=claims,
    )
    yield "supported_control", diagnosis
    for kind in ("mechanism", "configuration"):
        eligible = [
            item
            for item in answer.judgments
            if item.verdict == "irrelevant" and item.kind == kind
        ]
        if not eligible:
            continue
        decoy = eligible[-1]
        text = next(
            record.detail
            for records in case.tools.values()
            for record in records
            if record.evidence_id == decoy.evidence_id
        )
        changed = diagnosis.model_copy(deep=True)
        index = int(kind == "configuration")
        changed.claims[index] = ClaimCitation(
            kind=kind, evidence_id=decoy.evidence_id, quote=text
        )
        changed.evidence_ids[index] = decoy.evidence_id
        yield f"irrelevant_{kind}", changed


def run(client, cases, answers, log):
    totals = {}
    for model, rates in RATES.items():
        budget = Budget(rates=rates)
        counts = {
            "repairs": 0,
            "lost_support": 0,
            "unsupported_accepts": 0,
            "trials": 0,
            "estimated_usd": 0,
        }
        for case in cases:
            answer = answers[case.id]
            trace = [
                {
                    "type": "tool",
                    "ok": True,
                    "result": dispatch_observations(case, name, {}),
                }
                for name in case.tools
            ]
            records = {
                record.evidence_id: record.detail
                for entries in case.tools.values()
                for record in entries
            }
            for name, initial in variants(case, answer):
                review, review_trace, usage = investigate(
                    json.dumps(
                        {
                            "cause": initial.cause,
                            "claims": [claim.model_dump() for claim in initial.claims],
                            "observations": records,
                        }
                    ),
                    None,
                    client,
                    budget,
                    improved=False,
                    trace=[],
                    tools=[],
                    instructions=REVIEW_CITATIONS,
                    cause_contract=False,
                    response_model=CitationReview,
                    model=model,
                    max_requests=1,
                )
                revised = apply_citation_review(initial, review, records)
                before = grade_claims(initial, answer.cause, trace, answer.judgments)[
                    "passed"
                ]
                after = grade_claims(revised, answer.cause, trace, answer.judgments)[
                    "passed"
                ]
                counts["repairs"] += not before and after
                counts["lost_support"] += before and not after
                counts["unsupported_accepts"] += revised is not None and not after
                counts["trials"] += 1
                counts["estimated_usd"] += usage["estimated_usd"]
                log.write(
                    json.dumps(
                        {
                            "model": model,
                            "incident": case.id,
                            "variant": name,
                            "initial": initial.model_dump(),
                            "proposal": review.model_dump(),
                            "accepted": revised is not None,
                            "initial_supported": before,
                            "reviewed_supported": after,
                            "trace": review_trace,
                        }
                    )
                    + "\n"
                )
                log.flush()
        counts["estimated_usd"] = round(counts["estimated_usd"], 6)
        totals[model] = counts
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", type=Path)
    parser.add_argument("answers", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    cases, answers, manifest = load_suite(args.observations, args.answers)
    args.output.mkdir(parents=True)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (args.output / "runs.jsonl").open("x") as log:
        totals = run(OpenAI(max_retries=0, timeout=10), cases, answers, log)
    (args.output / "summary.json").write_text(json.dumps(totals, indent=2) + "\n")


if __name__ == "__main__":
    main()
