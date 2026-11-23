"""Deterministic evidence scope, rules baseline, and unresolved incident handoff."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from .assurance import check_citations, observed_records

Signal = Literal[
    "db_wait",
    "db_setting",
    "no_worker_activity",
    "worker_disabled",
    "upstream_mismatch",
    "route_misconfigured",
    "workload_healthy",
    "config_healthy",
]

RULES = {
    "db_latency": ("db_wait", "db_setting"),
    "worker_stopped": ("no_worker_activity", "worker_disabled"),
    "dependency_config": ("upstream_mismatch", "route_misconfigured"),
    "healthy": ("workload_healthy", "config_healthy"),
}


class EvidenceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: AwareDatetime
    service: str
    environment: str
    source: str
    signal: Signal | None = None
    rules_out: Literal["db_latency", "worker_stopped", "dependency_config"] | None = (
        None
    )


class IncidentWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: AwareDatetime
    end: AwareDatetime
    service: str
    environment: str

    @model_validator(mode="after")
    def validate_order(self):
        if self.start > self.end:
            raise ValueError("Incident end precedes start")
        return self

    def includes(self, context):
        return (
            context.service == self.service
            and context.environment == self.environment
            and self.start <= context.timestamp <= self.end
        )


def current_records(case, trace=None):
    """Return records attached to the configured service, environment, and window."""
    if case.window is None:
        raise ValueError("Evidence scope requires an explicit incident window")
    records = {
        record.evidence_id: record
        for records in case.tools.values()
        for record in records
        if record.context and case.window.includes(record.context)
    }
    if trace is None:
        return records
    observed, inconsistent = observed_records(trace)
    return {
        key: record
        for key, record in records.items()
        if key not in inconsistent and observed.get(key) == record.detail
    }


def evidence_decision(case, diagnosis=None, *, records=None):
    """Run the transparent rules baseline or assess a supplied diagnosis."""
    current = current_records(case) if records is None else records
    signals = {record.context.signal for record in current.values()}
    ruled_out = {record.context.rules_out for record in current.values()} - {None}
    supported = [cause for cause, rule in RULES.items() if set(rule) <= signals]
    cause = supported[0] if len(supported) == 1 else "unknown"
    conflicts = len(supported) > 1 or bool(ruled_out.intersection(supported))
    if conflicts:
        cause = "unknown"
    missing = {
        label: [signal for signal in rule if signal not in signals]
        for label, rule in RULES.items()
    }
    plausible = [
        label for label, rule in RULES.items() if set(rule) & signals and missing[label]
    ]
    if diagnosis is None:
        return {"cause": cause, "matched_rules": supported, "partial_rules": plausible}
    checks = check_citations(
        diagnosis, {key: record.detail for key, record in current.items()}, set()
    )
    cited_signals = {
        (claim.kind, current[claim.evidence_id].context.signal)
        for claim in diagnosis.claims
        if claim.evidence_id in current
    }
    confirmed = (
        cause != "unknown"
        and cause == diagnosis.cause
        and checks["passed"]
        and set(zip(("mechanism", "configuration"), RULES[cause], strict=True))
        <= cited_signals
    )
    confidence = (
        "confirmed"
        if confirmed
        else "plausible"
        if not conflicts and diagnosis.cause in plausible
        else "unresolved"
    )
    unresolved = confidence != "confirmed"
    next_tool = None
    if unresolved:
        next_tool = (
            "read_deployments"
            if any(RULES[label][1] in missing[label] for label in plausible)
            else "read_logs"
        )
    return {
        "confidence": confidence,
        "scope_checks": checks,
        "handoff": {
            "verified_evidence_ids": sorted(current),
            "conflicting_causes": supported if conflicts else [],
            "unconfirmed_candidates": plausible,
            "missing_signals": {label: missing[label] for label in plausible},
            "ruled_out": sorted(ruled_out.difference(supported)),
            "next_tool": next_tool,
        }
        if unresolved
        else None,
    }


def check_explanation(diagnosis, unsupported_phrases):
    """Report reviewer-specified unsupported phrases in free-text explanations."""
    if diagnosis is None:
        return None
    explanation = diagnosis.explanation.casefold()
    found = [
        phrase for phrase in unsupported_phrases if phrase.casefold() in explanation
    ]
    return {"passed": not found, "unsupported_phrases_found": found}
