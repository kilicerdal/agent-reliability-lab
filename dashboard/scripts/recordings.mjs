import {
  mkdir,
  readdir,
  readFile,
  copyFile,
  writeFile,
} from "node:fs/promises";
import { resolve, join } from "node:path";

const evidence = process.env.LAB_EVIDENCE_DIR || resolve("../evidence");
const destination = resolve("public/recordings");
await mkdir(destination, { recursive: true });
const captures = (await readdir(join(evidence, "runs")))
  .filter((name) => name.endsWith(".json"))
  .sort();
const runs = await Promise.all(
  captures.map(async (name) =>
    JSON.parse(await readFile(join(evidence, "runs", name), "utf8")),
  ),
);
await writeFile(
  join(destination, "v1-captures.json"),
  JSON.stringify(runs, null, 2) + "\n",
);
for (const [source, name] of [
  ["v2/summary.json", "v2-scorecard.json"],
  ["v2/runs.jsonl", "v2-traces.jsonl"],
  ["v3/boundaries.json", "v3-approval.json"],
  ["v3/prompt-trials.jsonl", "v3-prompt-trials.jsonl"],
  ["cause-contract-blind/paired.json", "blind-scorecard.json"],
  ["cause-contract-blind/runs.jsonl", "blind-traces.jsonl"],
  ["assurance/live-recovery/summary.json", "model-comparison.json"],
  ["assurance/live-recovery/runs.jsonl", "model-comparison-traces.jsonl"],
  ["assurance/database-boundary.json", "scoped-approval.json"],
]) {
  await copyFile(join(evidence, source), join(destination, name));
}

const comparison = JSON.parse(
  await readFile(join(evidence, "v2/summary.json"), "utf8"),
);
const trials = (await readFile(join(evidence, "v2/runs.jsonl"), "utf8"))
  .trim()
  .split("\n")
  .map((line) => JSON.parse(line));
const arms = ["baseline", "recovery"];
const incidentIds = [...new Set(trials.map((trial) => trial.incident))];
const incidents = incidentIds.map((id) => {
  const rows = trials.filter((trial) => trial.incident === id);
  const conditions = new Set(rows.map((trial) => trial.failure));
  const result = { id, condition: rows[0].failure };
  if (conditions.size !== 1)
    throw new Error(`Inconsistent tool conditions: ${id}`);
  for (const arm of arms) {
    const group = rows.filter((trial) => trial.arm === arm);
    const repetitions = new Set(group.map((trial) => trial.trial));
    if (
      group.length !== comparison.repeats ||
      repetitions.size !== comparison.repeats ||
      group.some(
        (trial) =>
          !Number.isInteger(trial.trial) ||
          trial.trial < 1 ||
          trial.trial > comparison.repeats,
      )
    )
      throw new Error(`Incomplete or duplicate trials: ${id}/${arm}`);
    result[arm] = {
      passed: group.filter((trial) => trial.strict_pass).length,
      total: group.length,
    };
  }
  return result;
});
for (const arm of arms) {
  const metrics = comparison.arms[arm].all;
  const rows = trials.filter((trial) => trial.arm === arm);
  if (
    rows.length !== metrics.runs ||
    trials.length !== incidentIds.length * arms.length * comparison.repeats ||
    ["strict_pass", "failure_exposed", "recovered"].some(
      (key) => rows.filter((row) => row[key]).length !== metrics[key],
    )
  ) {
    throw new Error(`V2 traces disagree with the scorecard: ${arm}`);
  }
}
const failures = trials.filter((trial) => !trial.strict_pass);
if (
  !failures.some(
    (trial) => trial.incident === "invoice-window" && trial.arm === "recovery",
  ) ||
  !runs.some((run) => run.scenario === "worker-failure")
) {
  throw new Error(
    "The showcase requires the recorded worker case and invoice-window failure.",
  );
}
const approval = JSON.parse(
  await readFile(join(evidence, "v3/boundaries.json"), "utf8"),
);
const blindScorecard = JSON.parse(
  await readFile(join(evidence, "cause-contract-blind/paired.json"), "utf8"),
);
const blindRuns = (
  await readFile(join(evidence, "cause-contract-blind/runs.jsonl"), "utf8")
)
  .trim()
  .split("\n")
  .map((line) => JSON.parse(line));
const pairs = Map.groupBy(blindRuns, (run) => `${run.incident}/${run.trial}`);
const corrections = [];
for (const pair of pairs.values()) {
  const previous = pair.find((run) => run.arm === "recovery");
  const revised = pair.find((run) => run.arm === "cause-contract");
  if (
    pair.length !== 2 ||
    !previous ||
    !revised ||
    previous.expected !== revised.expected
  ) {
    throw new Error("Incomplete or inconsistent blind trial pair");
  }
  if (!previous.strict_pass && revised.strict_pass) {
    corrections.push({ previous, revised });
  }
}
const byCause = Object.entries(blindScorecard.by_cause).map(
  ([cause, counts]) => {
    const row = {
      cause,
      previous: counts.recovery,
      revised: counts["cause-contract"],
    };
    for (const [arm, count] of [
      ["recovery", row.previous],
      ["cause-contract", row.revised],
    ]) {
      const trials = blindRuns.filter(
        (run) => run.arm === arm && run.expected === cause,
      );
      if (
        trials.length !== count.runs ||
        trials.filter((run) => run.strict_pass).length !== count.passed
      ) {
        throw new Error(
          `Blind trials disagree with the scorecard: ${cause}/${arm}`,
        );
      }
    }
    return row;
  },
);
if (
  byCause.reduce(
    (total, row) => total + row.previous.runs + row.revised.runs,
    0,
  ) !== blindRuns.length ||
  corrections.length !== blindScorecard.paired_outcomes.candidate_only
) {
  throw new Error(
    "Blind scorecard does not match the captured coverage or corrections",
  );
}
const blind = { byCause, corrections };
const recoverySummary = JSON.parse(
  await readFile(
    join(evidence, "assurance/live-recovery/summary.json"),
    "utf8",
  ),
);
const recoveryRuns = (
  await readFile(join(evidence, "assurance/live-recovery/runs.jsonl"), "utf8")
)
  .trim()
  .split("\n")
  .map((line) => JSON.parse(line));
const recoveryArms = Object.entries(recoverySummary).map(([key, totals]) => {
  const [model, prompt] = key.split("/");
  const rows = recoveryRuns.filter(
    (run) => run.model === model && run.prompt === prompt,
  );
  if (
    rows.length !== totals.runs ||
    rows.filter((run) => run.verdict.cause_correct).length !==
      totals.correct_cause ||
    rows.filter((run) => run.verdict.passed).length !== totals.supported
  ) {
    throw new Error(
      `Live recovery scorecard does not match the traces: ${key}`,
    );
  }
  return { model, prompt, ...totals };
});
if (
  recoveryArms.reduce((total, arm) => total + arm.runs, 0) !==
  recoveryRuns.length
) {
  throw new Error("Live recovery scorecard omits recorded runs");
}
const mismatch = recoveryRuns.find(
  (row) =>
    row.model === "gpt-6-luna" &&
    row.prompt === "check-support" &&
    row.verdict.cause_correct &&
    !row.verdict.passed &&
    row.verdict.claims.some((claim) => claim.verdict === "irrelevant"),
);
const counterpart =
  mismatch &&
  recoveryRuns.find(
    (row) =>
      row.model === "gpt-6.2-sol" &&
      row.prompt === mismatch.prompt &&
      row.incident === mismatch.incident &&
      row.repeat === mismatch.repeat &&
      row.verdict.passed,
  );
if (!counterpart)
  throw new Error(
    "The recovery comparison requires a matched citation example",
  );
const example = ({ model, diagnosis, verdict }) => ({
  model,
  cause: diagnosis.cause,
  claims: verdict.claims,
});
const recoveryComparison = {
  arms: recoveryArms,
  cases: new Set(recoveryRuns.map((row) => row.incident)).size,
  example: {
    incident: mismatch.incident,
    repeat: mismatch.repeat,
    supporting: example(counterpart),
    insufficient: example(mismatch),
  },
};
const readCapture = async (name) =>
  JSON.parse(await readFile(join(evidence, name), "utf8"));
const blindCitation = await readCapture(
  "assurance/citation-review-blind/summary.json",
);
const pairedSummary = await readCapture(
  "assurance/citation-review-paired/summary.json",
);
const pairedRows = (
  await readFile(
    join(evidence, "assurance/citation-review-paired/runs.jsonl"),
    "utf8",
  )
)
  .trim()
  .split("\n")
  .map(JSON.parse);
const pairedCitations = {
  blind: blindCitation,
  summary: pairedSummary,
  trials: pairedRows.map((row) => ({
    id: `${row.model}-${row.incident}-${row.repeat}`,
    model: row.model,
    incident: row.incident,
    cause: row.diagnosis?.cause ?? "No diagnosis",
    before: row.original_verdict,
    after: row.verdict,
    records: [
      ...new Map(
        row.trace
          .filter((event) => event.type === "tool" && event.ok)
          .flatMap((event) => event.result.records ?? [])
          .map((record) => [record.evidence_id, record]),
      ).values(),
    ],
  })),
};
await writeFile(
  resolve("app/showcase/recorded-data.json"),
  JSON.stringify({
    investigations: runs,
    comparison,
    incidents,
    failures,
    approval,
    blind,
    recoveryComparison,
    pairedCitations,
  }),
);
