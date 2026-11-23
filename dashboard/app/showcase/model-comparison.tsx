import styles from "./showcase.module.css";

type Arm = {
  model: string;
  prompt: string;
  runs: number;
  correct_cause: number;
  supported: number;
  median_ms: number;
  estimated_usd: number;
};
type Example = {
  model: string;
  cause: string;
  claims: {
    kind: string;
    evidence_id: string;
    quote: string;
    verdict: string;
  }[];
};
export type RecoveryComparison = {
  arms: Arm[];
  cases: number;
  example: {
    incident: string;
    repeat: number;
    supporting: Example;
    insufficient: Example;
  };
};
const models: Record<string, string> = {
  "gpt-6.2-sol": "GPT-6.2 Sol",
  "gpt-6-luna": "GPT-6 Luna",
};

export default function ModelComparison({
  comparison,
}: {
  comparison: RecoveryComparison;
}) {
  const { arms, cases, example } = comparison;
  const totals = arms.reduce(
    (sum, arm) => ({
      runs: sum.runs + arm.runs,
      correct: sum.correct + arm.correct_cause,
      supported: sum.supported + arm.supported,
    }),
    { runs: 0, correct: 0, supported: 0 },
  );
  return (
    <section
      id="model-comparison"
      className={styles.section}
      aria-labelledby="model-comparison-heading"
    >
      <div className={styles.sectionHeading}>
        <p className={styles.kicker}>
          Citation support · Live synthetic recovery
        </p>
        <h2 id="model-comparison-heading">Model comparison</h2>
        <p>
          Both models ran the same {cases} local recovery cases with two
          citation prompts. {totals.correct}/{totals.runs} runs chose the right
          cause. {totals.supported}/{totals.runs} also backed the diagnosis with
          supporting quotations.
        </p>
      </div>
      <div className={styles.panel}>
        <table className={`${styles.incidentTable} ${styles.modelTable}`}>
          <caption>
            Supported diagnoses, latency, and estimated API cost
          </caption>
          <thead>
            <tr>
              <th scope="col">Model and prompt</th>
              <th scope="col">Supported</th>
              <th scope="col">Median</th>
              <th scope="col">Cost for all runs</th>
            </tr>
          </thead>
          <tbody>
            {arms.map((arm) => (
              <tr key={`${arm.model}/${arm.prompt}`}>
                <th scope="row">
                  {models[arm.model] ?? arm.model}
                  <small>
                    {arm.prompt === "check-support"
                      ? "Explicit support check"
                      : "Basic citations"}
                  </small>
                </th>
                <td>
                  {arm.supported}/{arm.runs}
                </td>
                <td>{(arm.median_ms / 1000).toFixed(2)} s</td>
                <td>${arm.estimated_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className={styles.meta}>
          The cases exercised HTTP and PostgreSQL timeouts, missing telemetry,
          and stale conflicting evidence. Costs are estimated using standard
          token rates.
        </p>
      </div>
      <details className={`${styles.panel} ${styles.blindCorrection}`}>
        <summary>Compare citations for the same incident</summary>
        <p>
          Both models chose <code>{example.supporting.cause}</code> in{" "}
          {example.incident.replaceAll("-", " ")} · Trial {example.repeat}. The
          rubric checks whether each exact quotation supports its specific
          claim.
        </p>
        <div className={styles.compareGrid}>
          {[example.supporting, example.insufficient].map((run) => (
            <section
              key={run.model}
              aria-label={models[run.model]}
              className={styles.blindArm}
            >
              <h4>{models[run.model]}</h4>
              <ul className={styles.citations}>
                {run.claims.map((claim) => (
                  <li key={`${claim.kind}/${claim.evidence_id}`}>
                    <strong>{claim.kind}</strong>
                    {" · "}
                    <code>{claim.evidence_id}</code>
                    <p>{claim.quote}</p>
                    <p
                      className={
                        claim.verdict === "supports"
                          ? styles.pass
                          : styles.failure
                      }
                    >
                      {claim.verdict.replaceAll("_", " ")}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </details>
    </section>
  );
}
