# V1 verification — November 22, 2026

## Local verification

- Python 3.13, PostgreSQL 17 and the real local synthetic HTTP inventory dependency.
- 23 backend checks: workload reproduction, database read-only grants, experiment scoping, independent evaluator rejection cases, provider failure reservation, request limit and concurrent budget accounting.
- Strict TypeScript production build; Python lint/format checks and frontend formatting checks.
- Six Chromium browser executions across desktop and mobile emulation: capture navigation, citations and tool output, keyboard access, WCAG A/AA axe scans and explicit service-error handling. Not physical-device coverage.
- Four release captures from live GPT-6.2 Sol calls: database latency, disabled worker, incorrect inventory configuration and healthy control. All four passed their deterministic checks. This is one run per development case, not a general accuracy benchmark.
- Source digests, runtime versions and workload fingerprints are included in each capture. The offline evidence checker recalculates the verdicts and verifies the source digest without making model calls.

## Clean-environment verification

The `V1 verification` workflow runs both native service integration and Docker Compose integration. Inspect its actual status and logs before claiming either path passed. Local Docker Engine/Compose was unavailable during development; container verification is performed in GitHub Actions rather than inferred from a configuration file.

## Interpretation

The test harness intentionally creates understandable faults. Its oracle checks the known cause, observed citation IDs, required signal coverage, workload fingerprint equality and denied-tool attempts. It does not prove every sentence or all side effects. See [evaluation limits](evaluation.md).

The dashboard is a recorded-results viewer. CI never receives an API key and never invokes a paid model. Local spending-account records are excluded from the repository; per-capture token counts and conservative cost estimates remain visible as part of the synthetic experiment evidence.
