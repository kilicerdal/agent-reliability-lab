"""Validate and seal reviewer-provided observations and a separate scoring key."""

import argparse
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from backend.lab.contracts import Diagnosis
from backend.lab.tools import NAMES

from .assurance import EvidenceJudgment


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    detail: str = Field(min_length=8)


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    alert: str = Field(min_length=1)
    tools: dict[str, list[Observation]]


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    cause: str
    reviewer: str = Field(min_length=1)
    judgments: list[EvidenceJudgment]


def load_suite(cases_path, key_path):
    cases_bytes = cases_path.read_bytes()
    key_bytes = key_path.read_bytes()
    cases = [Incident.model_validate(item) for item in json.loads(cases_bytes)]
    answers = [Answer.model_validate(item) for item in json.loads(key_bytes)]
    key = {item.id: item for item in answers}
    if (
        not cases
        or len(cases) != len(answers)
        or len(key) != len(answers)
        or {case.id for case in cases} != key.keys()
    ):
        raise ValueError("Exactly one separate answer is required per unique incident")
    causes = set(Diagnosis.model_json_schema()["properties"]["cause"]["enum"])
    for case in cases:
        if set(case.tools) - set(NAMES):
            raise ValueError(f"{case.id}: unrecognized tool")
        records = {}
        for observations in case.tools.values():
            for observation in observations:
                previous = records.setdefault(
                    observation.evidence_id, observation.detail
                )
                if previous != observation.detail:
                    raise ValueError(f"{case.id}: evidence ID has inconsistent content")
        answer = key[case.id]
        judgments = {(item.kind, item.evidence_id) for item in answer.judgments}
        if (
            answer.cause not in causes
            or len(judgments) != len(answer.judgments)
            or any(item.evidence_id not in records for item in answer.judgments)
        ):
            raise ValueError(f"{case.id}: invalid answer or evidence judgment")
        if any(
            item.verdict == "supports"
            and (
                not item.required_excerpt
                or item.required_excerpt not in records[item.evidence_id]
            )
            for item in answer.judgments
        ):
            raise ValueError(
                f"{case.id}: supporting judgments need an exact reviewed excerpt"
            )
        if {item.kind for item in answer.judgments if item.verdict == "supports"} != {
            "mechanism",
            "configuration",
        }:
            raise ValueError(
                f"{case.id}: both claims need reviewed supporting evidence"
            )
    protocol = hashlib.sha256()
    for name in (
        "agent.py",
        "assurance.py",
        "recovery_benchmark.py",
        "../lab/agent.py",
        "../lab/tools.py",
    ):
        protocol.update(name.encode())
        protocol.update((Path(__file__).parent / name).read_bytes())
    manifest = {
        "cases": len(cases),
        "protocol_sha256": protocol.hexdigest(),
        "observations_sha256": hashlib.sha256(cases_bytes).hexdigest(),
        "answer_key_sha256": hashlib.sha256(key_bytes).hexdigest(),
    }
    return cases, key, manifest


def dispatch_observations(case, name, args):
    if name not in NAMES or args != {}:
        raise ValueError("Tool or arguments denied")
    return {"records": [record.model_dump() for record in case.tools.get(name, ())]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("key", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _, _, manifest = load_suite(args.cases, args.key)
    with args.output.open("x") as output:
        output.write(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
