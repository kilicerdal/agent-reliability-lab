# Citation review promotion criteria

The second-pass citation reviewer remains off by default. Use this policy to decide whether always-on review is eligible for manual promotion on a fresh independent paired benchmark. The gate runs offline and cannot change the application default.

## Offline regression suite

Run `python -m pytest backend/tests/test_assurance.py -k citation_defect_replay`. The suite starts from a supported diagnosis and changes one input at a time. It exercises backlog symptoms, stale settings, quotes that omit the supporting clause, swapped claim roles, fabricated quotes, unseen or unlisted IDs, conflicting records, and missing claim roles. It also replays a replacement proposal with the same cause and verifies that a conflicted source cannot be used to repair it.

The agent can check citation structure from its trace alone. The local check verifies observed IDs, exact quotes, consistent record contents, and both claim roles. It is used to identify malformed initial citations and to reject malformed replacement proposals. Actual support for the cause and role is evaluated against the separate rubric. A stale or irrelevant record can pass the local structural check.

## Policy citation-review-v1

Freeze these criteria before any qualifying run. Use the [independent reviewer kit](reviewer-kit/README.md) and run both Sol and Luna in paired mode so the baseline and review are scored from the same initial diagnosis.

| Requirement | Threshold |
| --- | --- |
| Independent cohort | At least 20 distinct incidents and at least 3 per cause, including `unknown`. A reviewer outside the lab attests that the suite was authored and graded before model outputs were available. |
| Coverage of weak citations | At least 5 distinct incidents per model with a correct initial cause and a failed initial claim. Repeated trials do not increase this coverage count. |
| Cause accuracy | No change in whether the cause was correct on any pair. The recorded cause label must also remain fixed. |
| Net support | More repaired diagnoses than lost passes for each model, with no decrease in support for any cause. |
| Lost support | At most 5% of initially supported diagnoses lose support per model. This includes false rejections and harmful replacements. |
| Execution | No recorded investigation or review execution errors. |
| Latency | Reviewed p95 end-to-end latency increases by at most 3 seconds per model. |
| Cost | Estimated average API cost increases by at most $0.005 per trial per model. |

The outside reviewer should supply a private JSON attestation alongside the evaluation. Set `reviewer` to their name or agreed identifier, set `independently_authored` and `graded_before_model_output` to true only if both statements are accurate, set `policy` to `citation-review-v1`, and set `suite` to the complete JSON object from the sealed manifest. The evaluator should verify the reviewer's identity and provenance through their agreed handoff. Matching the attestation to the sealed manifest does not authenticate the reviewer.

Use a capture directory containing `manifest.json`, `observations.json`, `answers.json`, `runs.jsonl`, and `summary.json`.

```sh
python -m backend.reliability.citation_promotion .private/independent-review/run \
  --attestation .private/independent-review/attestation.json
```

The command validates the capture and emits a JSON report with each gate result and per-cause support deltas. It exits successfully only when every criterion passes. Eligibility is a project decision rule. Report denominators and uncertainty before making broader reliability claims.

The recorded lab-authored paired suite is a useful negative control. It falls short of independent provenance and minimum case coverage. Every initial diagnosis already passed, so it also falls short of the weak-citation coverage and net repair criteria.
