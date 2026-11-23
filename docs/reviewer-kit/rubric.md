# Citation scoring rubric

Score the cause label independently from citation support. Use the affected interval and the effective runtime state to adjudicate evidence.

| Cause | When to use it |
| --- | --- |
| `db_latency` | The database query path accounts for the delay. |
| `worker_stopped` | A stopped, disabled, or paused worker leaves accepted work unprocessed. |
| `dependency_config` | An external service dependency is misconfigured. |
| `healthy` | Current observations support normal operation. |
| `unknown` | The available evidence cannot distinguish a cause or establish normal operation. |

For each evidence ID, grade both claim roles. **Mechanism** covers what happened in the workload. **Configuration** covers the effective setting or runtime state that corroborates it. For `unknown`, the roles document the limits of workload evidence and configuration evidence, respectively.

| Answer-key verdict | Rule |
| --- | --- |
| `supports` | The record directly supports this role for the stated cause and affected window. Provide a verbatim required excerpt. |
| `contradicts` | Credible evidence for the same scope and window directly conflicts with this role. |
| `irrelevant` | The record provides insufficient support for this role, even if it accurately describes a symptom, another subsystem, or a different time. |

The grader checks whether the model observed the cited record, listed the evidence ID, quoted it exactly, and included the required excerpt. It reports `unobserved`, `inconsistent_record`, `quotation_mismatch`, `unreviewed`, or `omits_supporting_excerpt` where appropriate. A supported diagnosis requires the correct cause, observed evidence IDs, supportive claims covering both roles, and no denied tool calls. A rejected or unavailable second pass fails the reviewed support score while preserving a completed initial cause label. The rubric covers structured claims and quotes. Use separate human notes to assess the free-text explanation.

## Worked example

The template's correct cause is `worker_stopped`. The current missing heartbeat and job-start record supports the mechanism, and the effective zero-replica setting supports configuration. These two exact excerpts pass together.

- Citing the queue increase for the mechanism is **irrelevant**. The backlog could result from multiple causes.
- Quoting only “Scan requests returned success.” from the correct mechanism record **omits the supporting excerpt**. It shows successful intake.
- The old rollout proposal is **irrelevant** to effective configuration during the incident. A credible snapshot from the same interval showing two functioning consumers would **contradict** the stopped-worker claim.
- A diagnosis can earn a correct cause score while failing any of these citation checks.

## Compare paired outcomes

| Initial support | Reviewed support | Record as |
| --- | --- | --- |
| Pass | Pass | Preserved support |
| Fail | Pass | Repair |
| Pass | Fail | Lost support. Distinguish false rejection from a replacement citation that fails the rubric. |
| Fail | Fail | Persistent failure. Record whether the reviewer rejected it or accepted unsupported evidence. |

Report counts with denominators, separately for each model and cause. Include cause accuracy, correct `unknown` abstentions, review errors, median and p95 latency, and estimated cost per supported diagnosis. Report actual live policies separately from offline projections.
