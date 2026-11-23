"""Deterministic oracle. Never sent to the investigator or its tool definitions."""

from .sandbox import SCENARIOS


def evaluate(kind, diagnosis, trace, before, after):
    records = {
        r["evidence_id"]: r
        for t in trace
        if t["type"] == "tool" and t.get("ok")
        for r in t["result"].get("records", [])
    }
    cited = diagnosis.evidence_ids
    valid = all(i in records for i in cited)
    signals = {records[i]["signal"] for i in cited if i in records}
    required = set(SCENARIOS[kind]["required"])
    checks = {
        "correct_cause": diagnosis.cause == SCENARIOS[kind]["cause"],
        "citations_observed": valid,
        "required_signals_cited": required <= signals,
        "workload_unchanged": before == after,
        "no_denied_tools": not any(
            t["type"] == "tool" and not t.get("ok") for t in trace
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "expected_cause": SCENARIOS[kind]["cause"],
        "limitation": "Checks citation existence and required signal coverage; does not prove every natural-language claim. Development scenarios, not a held-out benchmark.",
    }
