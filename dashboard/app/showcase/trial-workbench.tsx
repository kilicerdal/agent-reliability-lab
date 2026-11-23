"use client";

import { useState } from "react";
import type { Trial } from "./paired-citations";
import styles from "./showcase.module.css";

function exportComparison(trials: Trial[]) {
  const file = new Blob([JSON.stringify({ trials }, null, 2) + "\n"], {
    type: "application/json",
  });
  const url = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = url;
  link.download = "citation-trial-comparison.json";
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function TrialWorkbench({ trials }: { trials: Trial[] }) {
  const [cause, setCause] = useState("");
  const [failure, setFailure] = useState("");
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const choices = trials.filter(
    (trial) =>
      (!cause || trial.cause === cause) &&
      (!failure || trial.toolErrors.includes(failure)),
  );
  const first = choices.find((trial) => trial.id === left) ?? choices[0];
  const second =
    choices.find((trial) => trial.id === right) ?? choices[1] ?? first;
  const causes = [...new Set(trials.map((trial) => trial.cause))].sort();
  const failures = [
    ...new Set(trials.flatMap((trial) => trial.toolErrors)),
  ].sort();
  return (
    <section
      id="trial-workbench"
      className={styles.panel}
      aria-labelledby="trial-workbench-heading"
    >
      <h3 id="trial-workbench-heading">Compare recorded trials</h3>
      <p>
        Compare citations across the paired benchmark and selective stress run.
      </p>
      <p>
        <label htmlFor="workbench-cause">Filter by cause</label>{" "}
        <select
          id="workbench-cause"
          value={cause}
          onChange={(event) => setCause(event.target.value)}
        >
          <option value="">All causes</option>
          {causes.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </p>
      <p>
        <label htmlFor="workbench-failure">Filter by tool condition</label>{" "}
        <select
          id="workbench-failure"
          value={failure}
          onChange={(event) => setFailure(event.target.value)}
        >
          <option value="">All conditions</option>
          {failures.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </p>
      <p role="status">{choices.length} matching trials</p>
      {first && second && (
        <>
          <div className={styles.compareGrid}>
            {(
              [
                ["Trial A", first, setLeft],
                ["Trial B", second, setRight],
              ] as const
            ).map(([side, trial, select]) => (
              <div key={side}>
                <label>
                  {side}{" "}
                  <select
                    value={trial.id}
                    onChange={(event) => select(event.target.value)}
                  >
                    {choices.map((choice) => (
                      <option key={choice.id} value={choice.id}>
                        {choice.cohort} · {choice.model} · {choice.incident}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  Cause <code>{trial.cause}</code> · Before{" "}
                  {trial.before.passed ? "pass" : "fail"} · After{" "}
                  {trial.after.passed ? "pass" : "fail"}
                </p>
                <h4>Citations after review</h4>
                {trial.after.claims.map((claim, index) => (
                  <details key={index}>
                    <summary>
                      {claim.kind} · {claim.evidence_id} · {claim.verdict}
                    </summary>
                    <blockquote>{claim.quote}</blockquote>
                    <p>
                      {trial.records.find(
                        (record) => record.evidence_id === claim.evidence_id,
                      )?.detail ?? "Source was unavailable in this trial."}
                    </p>
                  </details>
                ))}
              </div>
            ))}
          </div>
          <p>
            <button
              type="button"
              onClick={() => exportComparison([first, second])}
            >
              Export trial comparison
            </button>
          </p>
        </>
      )}
    </section>
  );
}
