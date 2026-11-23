# Cause-label contract evaluation

A recorded V2 Invoice Window run correctly explained the SQL delay and still returned `dependency_config`. The deterministic evaluator failed the run because a downstream consumer sees the structured cause.

The candidate keeps the original tool loop, recovery instructions, output fields, enum values, validation, and grader. It adds definitions to the cause field and asks the model to match the mechanism in its explanation to the exact label. A configuration change may cause a database delay, stop a worker, or misroute a dependency. The affected subsystem determines the label. No expected answer is sent to the model.

## Protocol

The comparison uses GPT-6.2 Sol and the same frozen tool fixtures in both arms. It compares a fresh run of the V2 recovery prompt against the same prompt plus the new cause contract. Each arm runs three times on each of the eight original V2 holdout incidents. Invoice Window motivated the candidate, so this is a regression comparison on known fixtures. Keep the archived V2 result as historical context and use the fresh control for the head-to-head comparison.

```sh
python -m backend.reliability.evaluate --split holdout --compare cause-contract --repeats 3 --output .private/cause-contract-new
python -m backend.reliability.verify --evidence .private/cause-contract-new
```

The first command uses the project's existing budget and an authorized API key. The second reconstructs tool responses, grades, coverage, and the scorecard from the captured evidence offline.

[Scorecard](../evidence/cause-contract/summary.json) · [All paired traces](../evidence/cause-contract/runs.jsonl)

## Original fixtures

| Result | Current recovery prompt | Cause contract |
| --- | ---: | ---: |
| Correct, grounded diagnoses | 24/24 | 24/24 |
| Invoice Window | 3/3 | 3/3 |
| Recovery after tool failure or stale conflict | 18/18 | 18/18 |
| Median elapsed time | 6.99 s | 6.44 s |
| Estimated API cost | $0.193104 | $0.213446 |

The historical recovery run passed 23/24 overall and 2/3 on Invoice Window. The fresh control passed all three Invoice Window runs, so the original label error did not recur in this comparison. The tied scores provide no measured accuracy gain for the candidate on this suite.

## Fresh mixed-signal fixtures

Six additional synthetic fixtures exercise misleading alert context, configuration changes in different subsystems, stale summaries, and missing evidence. Both prompts use the same sealed fixture file and independently reset the replay tools before each trial. There are three repetitions per arm and incident.

```sh
python -m backend.reliability.evaluate --split holdout --fixtures backend/reliability/mixed-signals.json --compare cause-contract --repeats 3 --output .private/cause-contract-mixed-new
python -m backend.reliability.verify --fixtures backend/reliability/mixed-signals.json --evidence .private/cause-contract-mixed-new
```

[Fixture manifest](../backend/reliability/mixed-signals.json) · [Mixed-signal scorecard](../evidence/cause-contract-mixed/summary.json) · [All mixed-signal traces](../evidence/cause-contract-mixed/runs.jsonl)

| Result | Current recovery prompt | Cause contract |
| --- | ---: | ---: |
| Correct, grounded diagnoses | 17/18 | 18/18 |
| Spurious Stock Warning | 2/3 | 3/3 |
| Recovery among runs exposed to the affected tool | 14/15 | 13/13 |
| Median elapsed time | 7.31 s | 6.50 s |
| Estimated API cost | $0.158898 | $0.156842 |

The control's failed Spurious Stock Warning trial repeated the original failure pattern. It correctly cited a 700 ms SQL delay and healthy inventory, yet returned `dependency_config`. The candidate returned `db_latency` in all three repetitions. The recovery rates have different denominators because the two prompts sometimes chose different tools. Overall diagnosis uses the same planned denominator.

Across both comparisons, the 84 investigations used 357 API requests and an estimated $0.722290. The candidate remains opt-in. Its one-run gain on six fresh, hand-authored fixtures is a narrow result and supports a larger blind evaluation before adoption.
