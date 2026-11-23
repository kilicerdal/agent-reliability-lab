"""Run, resume, replay, or compare sealed incident benchmarks."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import recovery_benchmark
from .verify_paired_citations import verify


def compare(baseline, candidate):
    """Compare verified paired captures while holding incidents and keys fixed."""
    base_manifest, base_rows = baseline
    next_manifest, next_rows = candidate
    for field in ("observations_sha256", "answer_key_sha256"):
        if base_manifest["suite"][field] != next_manifest["suite"][field]:
            raise ValueError(f"Cannot compare captures with different {field}")

    def indexed(rows):
        by_trial = {(row["model"], row["incident"], row["repeat"]): row for row in rows}
        if len(by_trial) != len(rows):
            raise ValueError("Cannot compare duplicate trial IDs")
        return by_trial

    base = indexed(base_rows)
    changed = indexed(next_rows)
    if base.keys() != changed.keys():
        raise ValueError("Cannot compare mismatched trial coverage")
    totals = Counter()
    trials = []
    for model, incident, repeat in sorted(base):
        key = (model, incident, repeat)
        before, after = base[key], changed[key]
        cause_delta = int(after["verdict"]["cause_correct"]) - int(
            before["verdict"]["cause_correct"]
        )
        support_delta = int(after["verdict"]["passed"]) - int(
            before["verdict"]["passed"]
        )
        outcome = (
            "gained"
            if support_delta > 0
            else "lost"
            if support_delta < 0
            else "unchanged"
        )
        totals[f"support_{outcome}"] += 1
        totals["cause_regressions"] += cause_delta < 0
        trials.append(
            {
                "model": model,
                "incident": incident,
                "repeat": repeat,
                "expected_cause": before["expected"],
                "cause_before": (before["diagnosis"] or {}).get("cause"),
                "cause_after": (after["diagnosis"] or {}).get("cause"),
                "cause_accuracy_delta": cause_delta,
                "citation_support": outcome,
                "elapsed_ms_delta": after["elapsed_ms"] - before["elapsed_ms"],
                "estimated_usd_delta": round(
                    after["estimated_usd"] - before["estimated_usd"], 6
                ),
            }
        )
    counts = dict.fromkeys(
        ("support_gained", "support_lost", "support_unchanged", "cause_regressions"), 0
    )
    counts.update(totals)
    return {
        "same_protocol": base_manifest["suite"]["protocol_sha256"]
        == next_manifest["suite"]["protocol_sha256"],
        "counts": counts,
        "no_cause_or_support_regressions": not (
            counts["cause_regressions"] or counts["support_lost"]
        ),
        "trials": trials,
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="Start a run with the recovery benchmark options")
    commands.add_parser("resume", help="Resume a sealed run with its original options")
    replay = commands.add_parser("replay", help="Regrade a paired capture offline")
    replay.add_argument("capture", type=Path)
    comparison = commands.add_parser(
        "compare", help="Compare two paired captures offline"
    )
    comparison.add_argument("baseline", type=Path)
    comparison.add_argument("candidate", type=Path)
    comparison.add_argument("--fail-on-regression", action="store_true")
    if argv and argv[0] in {"run", "resume"}:
        options = argv[1:]
        if argv[0] == "resume":
            options = ["--resume", *options]
        recovery_benchmark.main(options)
        return 0

    args = parser.parse_args(argv)
    if not __debug__:
        parser.error(
            "Run without Python optimization so evidence verification stays enabled"
        )
    if args.command == "replay":
        verify(args.capture)
        return 0
    try:
        report = compare(
            verify(args.baseline, announce=False),
            verify(args.candidate, announce=False),
        )
    except (AssertionError, ValueError, OSError, KeyError) as exc:
        parser.error(
            f"Cannot compare paired captures: {exc or 'evidence verification failed'}"
        )
    print(json.dumps(report, indent=2))
    return int(
        args.fail_on_regression and not report["no_cause_or_support_regressions"]
    )


if __name__ == "__main__":
    raise SystemExit(main())
