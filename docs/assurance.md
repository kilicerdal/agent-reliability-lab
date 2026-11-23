# Agent assurance and recovery comparison

## Citation support

The original evaluator checks the selected cause and the presence of required evidence IDs. The assurance evaluator additionally requires a typed mechanism claim and a configuration claim. Each must cite an observed record and quote its text exactly. A separate rubric can classify that record as supportive, contradictory, irrelevant, or unreviewed for that claim. For reviewer-authored cases, a supportive verdict must also identify the exact excerpt the model quotation needs to contain.

This checks the structured claims and quotations. General factual review of the free-text explanation remains separate. Existing V1–V4 recordings retain their original grading rules.

## Independent benchmark intake

An independent reviewer supplies two JSON arrays. The observations file holds cases with `id`, `alert`, and `tools`. Each tool maps to observations with `evidence_id` and `detail`. The answer file holds `id`, `cause`, `reviewer`, and `judgments`. A judgment has `kind` (mechanism or configuration), `evidence_id`, `verdict` (supports, contradicts, or irrelevant), and an exact `required_excerpt` for supportive judgments. One supported claim of each kind is required. For a multi-fault case, the reviewer identifies the primary cause where the evidence supports one and uses `unknown` where it does not.

```sh
python -m backend.reliability.blind_intake observations.json answers.json --output .private/sealed-review.json
python -m backend.reliability.recovery_benchmark --cases observations.json --key answers.json --sealed .private/sealed-review.json --output .private/reviewer-run
```

The intake records separate hashes of the observations, answer key, and prompt protocol. The benchmark rejects a mismatch before sending any calls. Model requests get only the alert, the fixed tool catalogue, and tool responses containing the observations. The author-created local recovery cases exercise this harness. An independent reviewer still needs to author and adjudicate a separate suite.

## Local recovery comparison

The four cases use the same isolated order application, PostgreSQL, and HTTP inventory service as the lab. The named conditions cover a first-read HTTP timeout from a delayed endpoint, PostgreSQL statement cancellation, removal of telemetry before the investigation, and reconciliation of a stale summary with current worker evidence. Both timeout arms can retry the same read or seek other sufficient evidence. All configurations use the same case snapshots and scoring rubrics. This live comparison uses whole-record rubrics with exact quotes.

The comparison uses two models and two prompt configurations. Both prompts use the structured citation schema. The check-support prompt adds an explicit check for direct support and current evidence. The planned limits are six model requests, a 25-second investigation target, and a $0.03 estimated token cost target per investigation. The shared project ledger still gates requests. Costs use uncached standard token rates from the [OpenAI model catalog](https://developers.openai.com/api/docs/models).

```sh
python -m backend.reliability.recovery_benchmark --output .private/recovery-new
python -m backend.reliability.verify_recovery evidence/assurance/live-recovery
```

The first command uses the authorized key and the isolated application services. The second verifies the captured coverage, grades, observed timeout markers, cost estimates, and summary offline.

## Database-scoped approval

A trusted launcher provisions a PostgreSQL login scoped to exactly one experiment and passes only that connection to the MCP subprocess. PostgreSQL policies use the authenticated session identity for order, observation, and approval-request rows. The old shared MCP role is a group without login privileges. Worker restart requests bind the operation and experiment, and the operator's update still checks the request's age, eligibility, and prior use within one transaction.

The launcher removes the role on normal exit. Its password has a 20-minute expiry for new connections. Use an isolated PostgreSQL instance with password authentication and a trusted operator role for provisioning and approval. The operator harness supplied test confirmations by script. The [current capture](../evidence/assurance/database-boundary.json) records direct PostgreSQL read scope, denial of cross-experiment requests, expiration, concurrent confirmation, and idempotent order completion.

## Observed results

All 32 live runs chose the correct cause, including the insufficient-evidence abstentions. The claim grader found a difference in the evidence supporting those answers.

| Model / prompt | Supported diagnoses | Median time | Estimated cost for 8 runs |
| --- | ---: | ---: | ---: |
| GPT-6.2 Sol / basic citations | 8/8 | 7.77 s | $0.100656 |
| GPT-6.2 Sol / support check | 8/8 | 7.94 s | $0.105876 |
| GPT-6 Luna / basic citations | 3/8 | 6.72 s | $0.005799 |
| GPT-6 Luna / support check | 4/8 | 6.23 s | $0.005839 |

The 16 timeout trials exercised eight actual delayed HTTP reads and eight PostgreSQL statement cancellations. All eight Sol timeout trials passed the support rubric. Three of eight Luna timeout trials passed it. Across all conditions, Luna had 18 claim citations that matched an observed record but were irrelevant to the specific claim. The separate support check improved Luna by one investigation. Both Sol configurations passed all eight of their investigations. Every run met the measured latency and estimated-cost targets, and every workload fingerprint stayed unchanged.

These results describe four author-created, synthetic incidents with two repetitions per configuration. They support retaining Sol for this evidence requirement and testing on an independently authored suite before generalizing. Estimated API usage for the comparison was $0.218170.

[Comparison summary](../evidence/assurance/live-recovery/summary.json) · [32 recorded traces](../evidence/assurance/live-recovery/runs.jsonl) · [Frozen runtime manifest](../evidence/assurance/live-recovery/manifest.json)
