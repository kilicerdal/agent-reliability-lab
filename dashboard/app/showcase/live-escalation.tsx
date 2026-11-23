"use client";

import { useState } from "react";
import styles from "./showcase.module.css";

const labels = {
  luna: "Luna alone",
  sol: "Sol alone",
  luna_then_sol: "Luna → Sol",
};
type Policy = keyof typeof labels;
type Summary = {
  runs: number;
  cause_correct: number;
  supported: number;
  premature_causes: number;
  p95_ms: number;
  estimated_usd: number;
};
type Trial = {
  incident: string;
  expected: string;
  returned: string | null;
  cause_correct: boolean;
  supported: boolean;
  elapsed_ms: number;
  estimated_usd: number;
};
export type EscalationEvidence = {
  policies: Record<Policy, Summary>;
  trials: Record<Policy, Trial[]>;
  checks: Record<string, boolean>;
  eligible: boolean;
  escalations: number;
  missed_escalations: number;
  cost_savings_vs_sol: number;
};
const policies = Object.keys(labels) as Policy[];
const checks: Record<string, string> = {
  minimum_cohort: "Minimum incident coverage",
  cost: "At least 25% lower estimated cost than Sol",
  p95_latency: "p95 adds at most 3 seconds",
  preserve_case_accuracy_and_support:
    "Preserve each correct or supported Sol result",
  no_premature_cause: "No definitive causes on unresolved incidents",
  no_execution_failures: "No execution failures",
};
const base = process.env.NEXT_PUBLIC_LAB_BASE_PATH || "";

export default function LiveEscalation({
  evidence,
}: {
  evidence: EscalationEvidence;
}) {
  const [selected, select] = useState(evidence.trials.luna[0].incident);
  return (
    <section
      id="live-escalation"
      className={styles.section}
      aria-labelledby="live-escalation-heading"
    >
      <div className={styles.sectionHeading}>
        <h2 id="live-escalation-heading">Live escalation benchmark</h2>
        <p>
          A sealed, lab-authored synthetic suite. The escalation arm reused
          Luna’s first investigation and called Sol live only when confidence
          was unresolved or plausible.
        </p>
      </div>
      <div className={styles.panel}>
        <h3>
          {evidence.eligible
            ? "Passed the decision gate"
            : "Held at the decision gate"}
        </h3>
        <p>
          {evidence.escalations}/{evidence.policies.luna.runs} escalations ·{" "}
          {evidence.missed_escalations} missed opportunities to match a
          supported standalone Sol result.
        </p>
        <table className={`${styles.incidentTable} ${styles.modelTable}`}>
          <caption>Live model and escalation results</caption>
          <thead>
            <tr>
              <th scope="col">Policy</th>
              <th scope="col">Correct cause</th>
              <th scope="col">Supported</th>
              <th scope="col">p95</th>
              <th scope="col">Cost</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((policy) => {
              const row = evidence.policies[policy];
              return (
                <tr key={policy}>
                  <th scope="row">{labels[policy]}</th>
                  <td>
                    {row.cause_correct}/{row.runs}
                  </td>
                  <td>
                    {row.supported}/{row.runs}
                  </td>
                  <td>{(row.p95_ms / 1000).toFixed(2)} s</td>
                  <td>${row.estimated_usd.toFixed(4)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <details>
          <summary>Inspect the frozen criteria</summary>
          <ul>
            {Object.entries(evidence.checks).map(([criterion, pass]) => (
              <li key={criterion}>
                {checks[criterion] ?? criterion} · {pass ? "Passed" : "Failed"}
              </li>
            ))}
          </ul>
        </details>
        <p>
          <a href={`${base}/recordings/live-escalation-summary.json`}>
            Recorded summary
          </a>{" "}
          ·{" "}
          <a href={`${base}/recordings/live-escalation-traces.jsonl`}>
            Complete trial traces
          </a>
        </p>
      </div>
      <div className={styles.panel}>
        <h3>Inspect an escalation incident</h3>
        <label htmlFor="escalation-incident">Escalation incident</label>{" "}
        <select
          id="escalation-incident"
          value={selected}
          onChange={(event) => select(event.target.value)}
        >
          {evidence.trials.luna.map((row) => (
            <option key={row.incident}>{row.incident}</option>
          ))}
        </select>
        <ul>
          {policies.map((policy) => {
            const row = evidence.trials[policy].find(
              (trial) => trial.incident === selected,
            );
            if (!row) return null;
            return (
              <li key={policy}>
                <strong>{labels[policy]}</strong> returned{" "}
                <code>{row.returned ?? "No diagnosis"}</code> ·{" "}
                {row.supported ? "Supported" : "Failed support"} · expected{" "}
                <code>{row.expected}</code>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
