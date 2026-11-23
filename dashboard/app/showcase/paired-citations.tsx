"use client";

import { useState } from "react";
import type { RecoveryComparison } from "./model-comparison";
import TrialWorkbench from "./trial-workbench";
import styles from "./showcase.module.css";

type Claim = {
  kind: string;
  evidence_id: string;
  quote: string;
  verdict: string;
};
type Verdict = { cause_correct: boolean; passed: boolean; claims: Claim[] };
export type Trial = {
  cohort: string;
  toolErrors: string[];
  id: string;
  incident: string;
  model: string;
  cause: string;
  before: Verdict;
  after: Verdict;
  records: { evidence_id: string; detail: string }[];
};
type Totals = { supported: number; runs: number };
type Policy = Totals & {
  correct_cause: number;
  p95_ms: number;
  estimated_usd: number;
};
export type PairedEvidence = {
  blind: Record<string, Totals>;
  summary: Record<string, Policy>;
  trials: Trial[];
  stressTrials: Trial[];
};

const models = { "gpt-6.2-sol": "Sol", "gpt-6-luna": "Luna" };
const label = (model: string) => models[model as keyof typeof models] ?? model;
const ratio = (row: Totals) => `${row.supported}/${row.runs}`;
const repo = "https://github.com/kilicerdal/agent-reliability-lab/tree/main";

export default function PairedCitations({
  evidence,
  comparison,
}: {
  evidence: PairedEvidence;
  comparison: RecoveryComparison;
}) {
  const [selected, setSelected] = useState(evidence.trials[0].id);
  const [exercise, setExercise] = useState<"supported" | "unsupported" | null>(
    null,
  );
  const trial =
    evidence.trials.find((row) => row.id === selected) ?? evidence.trials[0];
  const weak = comparison.example.insufficient.claims.find(
    (claim) => claim.verdict === "irrelevant",
  );
  const originalLuna = comparison.arms.filter(
    (arm) => arm.model === "gpt-6-luna",
  );
  const worker = evidence.trials.filter(
    (row) => row.cause === "worker_stopped",
  );
  return (
    <section
      id="paired-citations"
      className={styles.section}
      aria-labelledby="paired-citations-heading"
    >
      <div className={styles.sectionHeading}>
        <h2 id="paired-citations-heading">Citation review evidence</h2>
        <p>
          Inspect how the same diagnosis scored before and after review. The
          viewer uses recorded trials.
        </p>
      </div>
      <ol className={styles.panel} aria-label="Citation regression timeline">
        <li>
          <strong>Original recovery benchmark.</strong> Luna had{" "}
          {originalLuna.reduce((sum, arm) => sum + arm.supported, 0)}/
          {originalLuna.reduce((sum, arm) => sum + arm.runs, 0)} supported
          diagnoses.
        </li>
        <li>
          <strong>First blind follow-up.</strong> Both models fell from{" "}
          {ratio(evidence.blind["gpt-6-luna/check-support"])} to{" "}
          {ratio(evidence.blind["gpt-6-luna/verify-citations"])} after review.
          The regressions involved worker stoppage.
        </li>
        <li>
          <strong>Paired follow-up.</strong>{" "}
          {worker.filter((row) => row.before.passed && row.after.passed).length}
          /{worker.length} worker trials passed both grades. Every initial
          diagnosis in this cohort had supported citations, leaving repair
          ability open.
        </li>
      </ol>
      <div className={styles.panel}>
        <h3>Paired release scorecard</h3>
        <table className={`${styles.incidentTable} ${styles.modelTable}`}>
          <caption>Citation support, cause accuracy, and review cost</caption>
          <thead>
            <tr>
              <th scope="col">Model and policy</th>
              <th scope="col">Supported</th>
              <th scope="col">Correct cause</th>
              <th scope="col">p95</th>
              <th scope="col">Estimated cost</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(evidence.summary).map(([arm, row]) => {
              const [model, policy] = arm.split("/");
              return (
                <tr key={arm}>
                  <th scope="row">
                    {label(model)} ·{" "}
                    {policy === "selective" ? "selective replay" : policy}
                  </th>
                  <td>{ratio(row)}</td>
                  <td>
                    {row.correct_cause}/{row.runs}
                  </td>
                  <td>{(row.p95_ms / 1000).toFixed(2)} s</td>
                  <td>${row.estimated_usd.toFixed(4)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p>
          <a href="#comparison">Tool recovery evidence</a> ·{" "}
          <a href="#approval">Approval controls</a>
          {" · "}
          <a href={`${repo}/docs/release-scorecard.md`}>Release scorecard</a>
          {" · "}
          <a href={`${repo}/docs/reproduce-evidence.md`}>
            Reproduction commands
          </a>{" "}
          ·{" "}
          <a href={`${repo}/evidence/assurance/citation-review-paired`}>
            Frozen inputs and traces
          </a>
        </p>
      </div>
      <div className={styles.panel}>
        <h3>Inspect a paired trial</h3>
        <p>
          <label htmlFor="paired-trial">Recorded trial</label>{" "}
          <select
            id="paired-trial"
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            {evidence.trials.map((row) => (
              <option key={row.id} value={row.id}>
                {label(row.model)} · {row.incident}
              </option>
            ))}
          </select>
        </p>
        <p>
          Fixed cause <code>{trial.cause}</code>
        </p>
        <div className={styles.compareGrid}>
          {(
            [
              ["Before review", trial.before],
              ["After review", trial.after],
            ] as const
          ).map(([stage, verdict]) => (
            <div key={stage}>
              <h4>
                {stage} · {verdict.passed ? "Supported" : "Failed support"}
              </h4>
              <ul>
                {verdict.claims.map((claim, index) => (
                  <li key={index}>
                    <a href={`#paired-source-${claim.evidence_id}`}>
                      {claim.kind} · {claim.evidence_id}
                    </a>
                    <blockquote>{claim.quote}</blockquote>
                    <p>{claim.verdict}</p>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <h4>Source records</h4>
        <dl>
          {trial.records.map((record) => (
            <div
              id={`paired-source-${record.evidence_id}`}
              key={record.evidence_id}
            >
              <dt>
                <code>{record.evidence_id}</code>
              </dt>
              <dd>{record.detail}</dd>
            </div>
          ))}
        </dl>
      </div>
      <TrialWorkbench trials={[...evidence.trials, ...evidence.stressTrials]} />
      {weak && (
        <div className={styles.panel}>
          <h3>Try grading a citation</h3>
          <p>
            The agent chose <code>{comparison.example.insufficient.cause}</code>
            . Does this quotation support the {weak.kind}?
          </p>
          <blockquote>{weak.quote}</blockquote>
          <button type="button" onClick={() => setExercise("supported")}>
            Supports the claim
          </button>{" "}
          <button type="button" onClick={() => setExercise("unsupported")}>
            Insufficient support
          </button>
          <p role="status">
            {exercise &&
              `${exercise === "unsupported" ? "Correct. " : ""}The rubric marked this record irrelevant to the claim. The agent selected the correct cause, but this citation did not support it.`}
          </p>
        </div>
      )}
    </section>
  );
}
