import styles from "./showcase.module.css";

type Arm = {
  runs: number;
  cause_correct: number;
  supported: number;
  p95_ms: number;
  estimated_usd: number;
  fresh_tool_reads: number;
};
export type HandoffEvidence = {
  arms: { restart: Arm; handoff: Arm };
  eligible: boolean;
};

export default function HandoffComparison({
  evidence,
}: {
  evidence: HandoffEvidence;
}) {
  const { restart, handoff } = evidence.arms;
  const base = process.env.NEXT_PUBLIC_LAB_BASE_PATH || "";
  return (
    <section
      id="evidence-handoff"
      className={styles.section}
      aria-labelledby="handoff-heading"
    >
      <div className={styles.sectionHeading}>
        <h2 id="handoff-heading">Evidence handoff experiment</h2>
        <p>
          Sol ran twice on each of four escalated incidents. Both arms started
          from the same recorded Luna investigation. The handoff arm received
          Luna’s original evidence and provisional diagnosis.
        </p>
      </div>
      <div className={styles.panel}>
        <h3>
          {evidence.eligible
            ? "Cleared the decision gate"
            : "Held at the decision gate"}
        </h3>
        <p>
          Fresh reads fell from {restart.fresh_tool_reads} to{" "}
          {handoff.fresh_tool_reads}. Estimated cost increased, and citation
          support declined. The default stayed unchanged.
        </p>
        <table className={`${styles.incidentTable} ${styles.modelTable}`}>
          <caption>
            Restart and handoff policy results across 12 incidents
          </caption>
          <thead>
            <tr>
              <th scope="col">Policy</th>
              <th scope="col">Correct cause</th>
              <th scope="col">Supported</th>
              <th scope="col">p95</th>
              <th scope="col">Est. cost</th>
            </tr>
          </thead>
          <tbody>
            {(
              [
                ["Restart Sol", restart],
                ["Pass Luna’s evidence to Sol", handoff],
              ] as const
            ).map(([name, row]) => (
              <tr key={name}>
                <th scope="row">{name}</th>
                <td>
                  {row.cause_correct}/{row.runs}
                </td>
                <td>
                  {row.supported}/{row.runs}
                </td>
                <td>{(row.p95_ms / 1000).toFixed(2)} s</td>
                <td>${row.estimated_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          Policy totals include the eight unchanged Luna trials. The handoff
          missed the citation-support and latency gates.
        </p>
        <p>
          <a href={`${base}/recordings/evidence-handoff-summary.json`}>
            Recorded handoff summary
          </a>{" "}
          ·{" "}
          <a href={`${base}/recordings/evidence-handoff-traces.jsonl`}>
            All eight Sol traces
          </a>
        </p>
      </div>
    </section>
  );
}
