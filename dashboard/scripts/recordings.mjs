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
const failure = trials.find(
  (trial) =>
    trial.incident === "invoice-window" &&
    trial.arm === "recovery" &&
    !trial.strict_pass &&
    trial.diagnosis,
);
if (!failure || !runs.some((run) => run.scenario === "worker-failure")) {
  throw new Error(
    "The showcase requires the recorded worker case and invoice-window failure.",
  );
}
const approval = JSON.parse(
  await readFile(join(evidence, "v3/boundaries.json"), "utf8"),
);
await writeFile(
  resolve("app/showcase/recorded-data.json"),
  JSON.stringify({ investigations: runs, comparison, failure, approval }),
);
