# Scoped evidence and selective review

The eight [synthetic stress incidents](../backend/reliability/quality-fixtures/observations.json) include a counterfactual pair with the same alert and distractors, overlapping SQL and worker faults, and partial, empty, timed-out, unavailable, and normalized malformed tool results. The [grading key](../backend/reliability/quality-fixtures/answers.json) grades both citation roles and defines example unsupported phrases. Open-ended factual review of the explanation still needs human judgment.

Scoped observations carry time, service, environment, and source. The rules baseline requires two corroborating current signals and returns unknown when evidence is insufficient or rules conflict. Confidence and triage handoffs use the records observed by the agent. The harness can request one additional unread tool when evidence is unresolved and the request budget allows it. A scripted test exercises that path. No trials triggered a targeted follow-up in this live cohort.

| Model | Live policy | Correct cause | Supported | Review calls | Median | Estimated cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Sol | Off | 8/8 | 8/8 | 0 | 8.95 s | $0.101298 |
| Sol | Selective | 8/8 | 8/8 | 3 | 9.80 s | $0.113432 |
| Luna | Off | 8/8 | 7/8 | 0 | 7.44 s | $0.005391 |
| Luna | Selective | 8/8 | 7/8 | 3 | 8.15 s | $0.005542 |

All configurations got both counterfactuals right. The rules also returned the keyed cause on all 32 trials. The rules received curated signal tags on records the models fetched, so this does not isolate the incremental value of model reasoning. Luna's selective arm missed one weak citation on the overlapping-fault incident. Review remains opt-in. [Per-cause counts, uncertainty intervals, and confidence results](../evidence/assurance/selective-stress/quality.json)

The [controlled citation challenge](../evidence/assurance/citation-challenge) used the public reviewer-kit incident. Both models repaired two deliberately irrelevant citations and preserved their supported control. This is a single lab-authored fixture.

## Resume and remediation

For a sealed external run, repeat the original benchmark command with `--resume`. The runner checks the manifest, locks the output directory, skips durably recorded trials, and replaces the summary atomically. If a trial was interrupted before its result was recorded, the in-flight marker blocks resuming until the uncertain usage is reconciled.

The PostgreSQL integration test interrupts approval after worker state changes and before the audit write. The transaction rolls back and a retry applies exactly once. A simulated inventory fault then leaves the order queued after the restart. Recovery is recorded only after the order completes. [Recorded remediation outcome](../evidence/assurance/remediation-outcome.json)

The next routing revision adds two deterministic triggers for scoped incidents. Review runs when observed current evidence supports competing causes, or when a citation falls outside the incident's time window, service, or environment. The offline regression replays Luna's recorded overlapping-fault miss and a clean control. It checks routing only. The live results above predate this revision.

Targeted-read trials now capture the score before requesting the extra evidence and the score immediately after investigation, before second-pass citation review. The controlled counterfactual test starts both variants from the same unresolved diagnosis. A current zero-replica observation supports switching to `worker_stopped`. A record showing that effective settings are missing supports retaining `unknown`. The test uses scripted model responses and measures the harness behavior. Live accuracy gains remain unmeasured.
