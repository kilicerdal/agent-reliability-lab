# Sealed benchmark workflow

Start with separate observations and an answer key from the [reviewer kit](reviewer-kit/README.md). Seal the files on the checkout that will run the benchmark. The paired run can keep the frozen inputs alongside the output. Use a private destination because the capture includes the answer key.

```sh
python -m backend.reliability.benchmark run --paired-citation-review --bundle \
  --repeats 1 --cases observations.json --key answers.json --sealed sealed.json \
  --env-file .env.local --output .private/paired-candidate
```

To resume, use `benchmark resume` with the same options and output directory. The runner checks the seal and run configuration, skips completed trials, and pauses if the previous attempt left uncertain API usage.

Regrade or compare recorded paired captures offline.

```sh
python -m backend.reliability.benchmark replay .private/paired-candidate
python -m backend.reliability.benchmark compare .private/paired-baseline .private/paired-candidate \
  --fail-on-regression
```

Comparison requires matching observation and answer-key digests and matching model, incident, and repeat coverage. Each row reports what changed in cause, support, elapsed time, and estimated cost. A protocol change is reported separately. The regression exit code fails on any lost supported diagnosis or newly incorrect cause. Use the [promotion criteria](citation-promotion.md) for a broader eligibility decision.

## Controlled live reads

Two counterfactual cases start from the same fixed `unknown` diagnosis. The stop arm makes no model call. Targeted reassessment gets the deployment read. Broad reassessment also gets the queue and health results. Both reassessment arms make one model call.

| Model | Stop cause / support | Targeted cause / support | Broad cause / support |
| --- | --- | --- | --- |
| Sol | 1/2 / 0/2 | 2/2 / 2/2 | 2/2 / 2/2 |
| Luna | 1/2 / 0/2 | 1/2 / 1/2 | 2/2 / 2/2 |

Luna's targeted arm chose worker stoppage when the effective configuration was missing. The broad arm's additional sources were empty in this pair, so the result does not establish an advantage for broad evidence. The cohort contains one repetition. Together the eight reassessments used an estimated $0.016533. [Traces, latency, and cost](../evidence/assurance/targeted-read-controlled)

## Recorded decision policy comparison

The offline escalation replay uses the scoped stress capture. It substitutes the corresponding recorded Sol run when Luna's confidence is plausible or unresolved. It estimates latency and cost by summing serial requests. The rules baseline receives curated signals from the records Luna fetched.

| Policy | Cause | Citation support | Estimated p95 | Estimated cost for eight trials |
| --- | --- | --- | --- | --- |
| Rules on Luna observations | 8/8 | Not graded | — | — |
| Luna | 8/8 | 7/8 | 9.25 s | $0.005391 |
| Sol | 8/8 | 8/8 | 10.45 s | $0.101298 |
| Luna then Sol | 8/8 | 8/8 | 18.12 s | $0.061941 |

The replay escalated four of eight cases. Live escalation, a fresh independent cohort, and an unassisted rules baseline are still needed to assess the policy. [Decision replay and per-trial results](../evidence/assurance/selective-stress/decision-policies.json)

## Stateful remediation scenarios

Run `python -m backend.controls.remediation_lab --output .private/remediation-matrix.json` against the isolated PostgreSQL and HTTP inventory services. The suite advances the workload while a restart awaits approval, uses the scoped MCP request and operator confirmation, retries the approval, then checks actual queue outcomes. The normal worker restart recovered the workload. The compound inventory fault left the order queued even though the approval applied exactly once. [Recorded state transitions](../evidence/assurance/remediation-matrix.json)

## Explanation assurance

An independent reviewer can use `python -m backend.reliability.explanation_audit packet.json` to validate their explanation annotations offline. The packet has an `explanation` string, the tool `trace`, and ordered `annotations`. Each annotation gives the exact explanation `text`, a `kind` (timestamp, configuration, causality, recovery, or other), and a human `verdict` (supports, contradicts, or insufficient). For a supported or contradicted assertion, include the observed `evidence_id` and exact `quote`. The command reports gaps in annotation coverage and verifies the referenced quotes. The reviewer supplies the semantic grade.

The static workbench compares any two available paired or selective stress trials. Visitors can filter by cause or recorded tool condition and download the selected comparison as JSON. This runs entirely on captured data.

## Remaining evaluation work

The independent suite requires an outside reviewer to author and seal the cases. Live escalation and a broader targeted-read cohort remain unmeasured. The stateful suite scores operator approval and workload recovery. An agent-driven investigation across state transitions still needs an evaluation, and the explanation audit still needs independently annotated model outputs.
