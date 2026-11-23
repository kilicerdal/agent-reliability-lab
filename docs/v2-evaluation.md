# V2 reliability evaluation

V2 compares the V1 prompt with the same prompt plus explicit recovery instructions. Both arms use the same GPT-6.2 Sol model, read-only tool definitions, structured diagnosis schema, request limits and deterministic incident fixtures. The extra instructions ask the model to retry transient timeouts once, use other evidence sources when a source is unavailable, prefer current direct observations to stale summaries, and abstain when evidence is insufficient.

## Design

The twelve hand-authored synthetic incidents are split into four development cases and eight holdout cases. Development used one run per arm and case. The holdout protocol uses three fresh investigations per arm and case, 24 per arm and 48 total. Every investigation starts with fresh tool state. The baseline and recovery arms alternate launch order by case and repetition. Model requests use the approved project credentials and existing SQLite budget controls. The published fixture hash identifies the incident manifest frozen before live trials.

These are replayed tool fixtures, distinct from the PostgreSQL and HTTP workload in V1. A timeout is a deterministic tool response that succeeds on the next call, so elapsed time does not include real waiting for a timed-out dependency. A missing source stays unavailable on repeat calls. Stale conflicting records are labeled as historical. The insufficient-evidence case tests abstention using records documenting the telemetry gap. The agent receives the alert and only the records returned by its own tools. The fixture manifest is public and the holdout was authored in the same implementation session as the protocol. The split measures behavior on fixtures excluded from development runs.

## Measures

- **Correct diagnosis** requires an exact match with the expected cause, including `unknown` for the insufficient-evidence scenario.
- **Strict pass** also requires both current record IDs, only observed citations, and no denied tool attempts. The IDs establish evidence coverage. Free-text explanations and alternatives are outside this check.
- **Failure exposure** counts investigations whose calls actually reached the affected source. **Recovery** requires exposure and a strict pass. A timeout can recover via a successful retry or sufficient evidence from other tools. The timeout retry tally is reported separately.
- **Median elapsed time** covers model and tool orchestration under four-way concurrency. **Estimated API cost** uses the V1 standard token rates. Repeats of the same fixture and shared observations across tools limit statistical independence. The scorecard reports counts for this suite.

## Held-out results

| Measure | V1 prompt | Recovery-guided prompt |
| --- | ---: | ---: |
| Correct structured cause and strict pass | 19/24 (79.2%) | 23/24 (95.8%) |
| Recovery after exposure | 13/18 (72.2%) | 17/18 (94.4%) |
| Transient timeout retried | 6/6 | 6/6 |
| Correct, grounded result after timeout | 3/6 | 5/6 |
| Correct, grounded result after missing source | 4/6 | 6/6 |
| Correct, grounded result after stale conflict | 6/6 | 6/6 |
| Correct abstention on insufficient evidence | 3/3 | 3/3 |
| Median investigation latency | 6.12 s | 6.48 s |
| Estimated API cost | $0.1693 | $0.1932 |

The recovery instructions improved the measured result by four runs. Both arms retried every timeout, so the difference in timeout recovery was in the final diagnosis. In all three baseline runs and one recovery-guided run of `invoice-window`, the explanation identified the configured SQL delay while the structured cause was `dependency_config`. Two baseline runs of `orphan-alert` similarly explained the disabled worker but assigned the dependency label. These are failures of the structured contract.

Both arms completed 4/4 development runs. The holdout comprises only eight distinct incidents and shares V1's cause categories. The percentages describe these repeated fixture runs. Tool-failure recovery here does not measure resilience to actual service outages.

## Run and inspect

Run from the repository root with the V1 Python dependencies. Point the command at a new output directory. With an authorized key available in the environment, the following runs the complete holdout and writes one JSONL trace per investigation and a JSON summary.

```sh
python -m backend.reliability.evaluate --split holdout --repeats 3 --output .private/v2-new
```

Run `python -m backend.reliability.verify` to recalculate the captured grades and scorecard offline.

The captured holdout results live in [evidence/v2](../evidence/v2/). V1 captures remain in their original directory and continue to work in the recorded viewer.
