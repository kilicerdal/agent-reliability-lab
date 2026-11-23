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
await writeFile(
  resolve("app/showcase/recorded-data.json"),
  JSON.stringify({
    investigations: runs,
    comparison,
    incidents,
    failures,
    approval,
  }),
);
