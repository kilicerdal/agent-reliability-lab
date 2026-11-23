# What the evaluator checks

The harness chooses and reproduces a fault. The agent receives only an alert and four no-argument, read-only tools, bound by the application to one experiment. The expected cause is not included in the prompt, tool descriptions or tool outputs.

A passing result requires all five checks:

1. The structured cause equals the injected cause.
2. Every cited `obs-N` ID was present in tool output seen during this investigation.
3. The cited records cover the scenario’s required signals: failure/healthy behavior and the relevant configuration change, as appropriate.
4. A SHA-256 fingerprint of order state, service configuration and observations is identical before and after investigation.
5. No denied tool call was attempted.

The oracle does **not** perform semantic entailment of every sentence. A valid citation can still accompany an overstated explanation. Rejection fixtures test wrong causes, missing required signals, invented citations, changed state and denied operations. Positive unit fixtures verify the checker; they are not model evaluation results.

The four included model captures are one run per authored development scenario. They establish those runs only. No success percentage should be advertised as general accuracy. These cases are transparent and intentionally easy to inspect; the selected cause enum constrains the task. V2 adds held-out incidents, repeated trials and baselines before comparative claims.

Fingerprint coverage excludes unrelated database tables and the API cost ledger. It detects changes in the modeled workload, not every possible side effect. Stable evidence IDs are scoped by the application; the database role itself can read the two granted tables across experiments. This is not tenant isolation. The agent has no general SQL, shell, filesystem or remediation tool.

Trace entries contain model/request metadata, token counts, elapsed time and tool inputs/outputs. They do not include private chain-of-thought. All logs, orders and dependency responses are synthetic. The captured mode is live-model/real-local-workload, while dashboard browsing is recorded replay.
