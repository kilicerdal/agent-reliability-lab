# Independent blind incident reviewer kit

Use this kit to test whether a citation reviewer repairs weak evidence and preserves citations that already support a diagnosis. An outside reviewer authors and adjudicates the cases before seeing any model output. Authoring, sealing, and offline grading require no API key.

## 1. Author the incidents

Copy the [observations template](observations.template.json) and [answer key template](answers.template.json) into a private directory and replace the worked example with new incidents. Use synthetic or appropriately sanitized records. Keep incident and evidence IDs neutral. Both files are JSON arrays, and their incident IDs must match.

- Write an alert that describes the symptom or operator question. Put evidence behind one or more of `read_logs`, `read_deployments`, `read_queue`, and `read_health`. Each record contains an `evidence_id` and a `detail` string. Use empty arrays for tools with no records.
- Include both clean controls and cases with plausible weak citations. Useful cases include backlog without a worker state, stale rollout intent versus effective settings, healthy subsystems beside a real failure, an exact quote that skips the decisive clause, and conflicting measurements for the same window.
- Include cases across the five cause labels in the [rubric](rubric.md). For mixed faults, identify the primary cause only when current evidence distinguishes it. For an `unknown` case, supply records showing the specific gaps or unresolved conflict for each claim role.
- Label each evidence record separately for mechanism and configuration. Write the smallest exact excerpt that is sufficient for each supportive row, at least eight characters. If another record independently supports the same role, mark it supportive too.
- In the private [adjudication worksheet](adjudication.template.md), record why the likely weak citation fails and what an acceptable citation would show. Have a second reader resolve disagreements before sealing when one is available.

## 2. Seal the observations and key

From the repository root, use Python 3.13 or 3.14 with the dependencies in `requirements.lock` installed. Record the Git commit so the operator uses the same prompt protocol. The commands below make private copies of the examples first. Edit the private copies before running the seal command.

```sh
umask 077
mkdir -p .private
mkdir -m 700 .private/independent-review &&
cp docs/reviewer-kit/observations.template.json .private/independent-review/observations.json &&
cp docs/reviewer-kit/answers.template.json .private/independent-review/answers.json
git rev-parse HEAD
```

After editing both private copies, seal them.

```sh
python -m backend.reliability.blind_intake \
  .private/independent-review/observations.json \
  .private/independent-review/answers.json \
  --output .private/independent-review/sealed.json
```

The seal validates incident IDs, tool names, causes, evidence IDs, and the supporting excerpts. It records SHA-256 digests of the two exact files and the benchmark protocol. Share the observations, manifest, and Git commit with the operator. Keep the key and worksheet private until the cohort is frozen, then transfer the key privately to the evaluator running the harness. The harness needs the key locally to verify the seal and score outputs. The model receives alerts and tool observations. The seal detects changes, and file access controls keep the key private. If any sealed file or the protocol changes, issue a new manifest and document the change before running either arm.

## 3. Run and grade the frozen suite

The operator runs the paired mode at the recorded checkout. Choose and record the repeat count before running. The live benchmark uses API credits. An evaluator can inspect completed captures offline.

```sh
python -m backend.reliability.recovery_benchmark \
  --paired-citation-review --repeats 1 \
  --cases .private/independent-review/observations.json \
  --key .private/independent-review/answers.json \
  --sealed .private/independent-review/sealed.json \
  --output .private/independent-review/run
```

The harness scores the same diagnosis before and after citation review. Use the [rubric](rubric.md) to audit the per-claim grades and the worksheet to document repairs, false rejections, and unsupported citations that remain. Leave the frozen key unchanged when investigating discrepancies. Record disagreements separately and adjudicate a new version if necessary. Keep raw traces private while review is ongoing because they include expected causes and rubric judgments.

For the single-repeat command above, regrade the capture offline by placing the original observations and answer key alongside the output and running the verifier.

```sh
cp .private/independent-review/observations.json .private/independent-review/answers.json .private/independent-review/run/
python -m backend.reliability.verify_paired_citations .private/independent-review/run
```
