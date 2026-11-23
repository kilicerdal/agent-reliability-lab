"""Audit independently annotated explanation spans against observed records."""

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .assurance import observed_records


class Assertion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    kind: Literal["timestamp", "configuration", "causality", "recovery", "other"]
    verdict: Literal["supports", "contradicts", "insufficient"]
    evidence_id: str | None = None
    quote: str | None = None


def audit(explanation, trace, annotations):
    """Reject uncovered text and citations that cannot be verified in the trace."""
    records, conflicts = observed_records(trace)
    cursor = 0
    uncovered = []
    results = []
    for annotation in annotations:
        start = explanation.find(annotation.text, cursor)
        if start < 0:
            raise ValueError("Explanation spans must occur verbatim and in order")
        if gap := explanation[cursor:start].strip():
            uncovered.append(gap)
        cursor = start + len(annotation.text)
        status = annotation.verdict
        if status in {"supports", "contradicts"}:
            record = records.get(annotation.evidence_id)
            if record is None or annotation.evidence_id in conflicts:
                status = "unverifiable_record"
            elif not annotation.quote or annotation.quote not in record:
                status = "unverifiable_quote"
        results.append(
            {
                "text": annotation.text,
                "kind": annotation.kind,
                "verdict": status,
                "evidence_id": annotation.evidence_id,
                "quote": annotation.quote,
            }
        )
    if tail := explanation[cursor:].strip():
        uncovered.append(tail)
    return {
        "passed": bool(results)
        and not uncovered
        and all(row["verdict"] == "supports" for row in results),
        "unreviewed_spans": uncovered,
        "assertions": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packet", type=Path, help="JSON object with explanation, trace, and annotations"
    )
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text())
    result = audit(
        packet["explanation"],
        packet["trace"],
        [Assertion.model_validate(row) for row in packet["annotations"]],
    )
    print(json.dumps(result, indent=2))
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
