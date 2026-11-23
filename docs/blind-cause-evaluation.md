# Blind cause-label evaluation

Both prompts and the grader are fixed before the run. The new fixture file has 25 cases, five per output label. Run each case twice per arm for 100 investigations. Both arms receive the same permitted tool evidence. The model receives no fixture IDs, expected labels, or grading criteria. The project author created and labeled these synthetic cases. The model is blinded to the answer key. Independent human review is outside this experiment.

The primary metric is the existing strict pass. Compare the same case and repetition across prompts, report discordant pairs, and report results for all five expected labels. Also report SQL-to-dependency mislabels, correct `unknown` abstentions, and grounded recoveries among runs exposed to a tool failure. Group repeated runs by incident when discussing the strength of the evidence.

The candidate clears this local promotion gate only if it adds at least three strict passes out of 50, improves SQL diagnoses, and matches or exceeds every other cause category. A successful gate would support a separate decision about changing the default.

Frozen fixture SHA-256: `d7b528dcd66f9d75d50f708a2035ba7fa5bd2d486ecffe04a040288fb00a5cb3`.

## Results

| Expected label | Current recovery prompt | Cause-label contract |
| --- | ---: | ---: |
| Database latency | 9/10 | 10/10 |
| Worker stopped | 8/10 | 10/10 |
| Dependency configuration | 10/10 | 10/10 |
| Healthy | 10/10 | 10/10 |
| Unknown | 10/10 | 10/10 |
| **Strict passes** | **47/50** | **50/50** |

Both arms passed 47 pairs. The candidate alone passed three pairs across three distinct incidents. All three control misses returned the dependency label while describing a different mechanism and citing the required observations. One described a 900 ms SQL delay and healthy inventory. The other two explained a disabled fulfillment worker. The candidate passed every paired counterpart. Both arms correctly abstained in all ten insufficient-evidence runs.

The control recovered in 38/40 runs exposed to a tool failure or stale conflict. The candidate recovered in 40/40. Median elapsed times were 6.63 s and 6.13 s under four-way concurrency. The comparison used 417 API requests at an estimated $0.845116.

The result meets the frozen local gate. The candidate improved database and worker labels and matched the other three categories. These runs cover 25 hand-authored synthetic cases with two repetitions each. The cause-label contract is now the live runner default. Historical comparison commands keep their original arms. The result is scoped to the recorded synthetic fixtures.

## Reproduce

```sh
python -m backend.reliability.evaluate --split holdout --fixtures backend/reliability/blind-cause-fixtures.json --compare cause-contract --repeats 2 --output .private/blind-cause-new
python -m backend.reliability.paired_report --fixtures backend/reliability/blind-cause-fixtures.json --evidence evidence/cause-contract-blind
```

The first command makes live model calls with the approved budget. The second verifies the recorded tool responses, verdicts, and scorecard offline before computing the paired report.

[Paired results](../evidence/cause-contract-blind/paired.json) · [All 100 traces](../evidence/cause-contract-blind/runs.jsonl)
