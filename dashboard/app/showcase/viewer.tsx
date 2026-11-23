"use client";

import { useState, useSyncExternalStore } from "react";
import styles from "./showcase.module.css";
import HandoffComparison, { type HandoffEvidence } from "./handoff-comparison";
import LiveEscalation, { type EscalationEvidence } from "./live-escalation";
import PairedCitations, { type PairedEvidence } from "./paired-citations";
import ModelComparison, { type RecoveryComparison } from "./model-comparison";

type RecordItem = {
  evidence_id: string;
  service?: string;
  signal: string;
  detail: string;
};
type Trace = {
  type: string;
  name?: string;
  model?: string;
  elapsed_ms: number;
  result?: { records?: RecordItem[]; error?: string };
};
type Diagnosis = { cause: string; explanation: string; evidence_ids: string[] };
export type Investigation = {
  id: string;
  scenario: string;
  diagnosis: Diagnosis;
  trace: Trace[];
  usage: { model: string; elapsed_ms: number };
  verdict: {
    expected_cause: string;
    passed: boolean;
    checks: Record<string, boolean>;
  };
};
type Counts = {
  runs: number;
  strict_pass: number;
  failure_exposed: number;
  recovered: number;
  median_ms: number;
};
export type Comparison = {
  repeats: number;
  arms: Record<"baseline" | "recovery", Record<string, Counts>>;
};
type Incident = {
  id: string;
  condition: string;
  baseline: { passed: number; total: number };
  recovery: { passed: number; total: number };
};
const conditions: Record<string, string> = {
  timeout: "Transient timeout",
  missing: "Unavailable source",
  conflict: "Stale conflicting record",
  insufficient: "Insufficient evidence",
  none: "No injected tool condition",
};
const armLabels: Record<string, string> = {
  baseline: "V1 prompt",
  recovery: "Recovery prompt",
};
const failureKey = (run: Failure) => `${run.incident}/${run.arm}/${run.trial}`;
const trialId = (key: string) => `failed-trial-${key}`;
const trialHref = (key: string) => `#${trialId(key)}`;
const trialFromUrl = () => window.location.hash.slice(1);
const noTrial = () => "";
const subscribeToHydration = () => () => {};
function subscribeToTrial(callback: () => void) {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}
type Failure = {
  incident: string;
  arm: string;
  trial: number;
  strict_pass: boolean;
  expected: string;
  diagnosis: Diagnosis | null;
  trace: Trace[];
};
type WorkerState = {
  worker_enabled: boolean;
  order_status: string;
  restart_events: number;
  completion_events: number;
};
export type Approval = {
  protocol: string;
  states: Record<string, WorkerState>;
  concurrent_results: string[];
  denied_mcp_calls: Record<string, boolean>;
  denied_database_sqlstates: Record<string, string>;
  expired_result: string;
};
const labels: Record<string, string> = {
  "worker-failure": "Worker unavailable",
  "database-slowdown": "Database slowdown",
  "dependency-failure": "Dependency failure",
  healthy: "Healthy control",
};
const order = Object.keys(labels);
const stages = [
  {
    key: "before_request",
    title: "Incident",
    detail: "The worker was disabled and the order waited in the queue.",
  },
  {
    key: "pending",
    title: "Request pending",
    detail: "The MCP tool filed a restart request for the bound experiment.",
  },
  {
    key: "after_wrong_confirmation",
    title: "Wrong confirmation",
    detail:
      "The operator command rejected an experiment ID that did not match.",
  },
  {
    key: "after_approval",
    title: "Approval applied",
    detail:
      "Two concurrent confirmations returned one applied result and one already applied result.",
  },
  {
    key: "after_two_ticks",
    title: "Order completed",
    detail: "The worker polled twice. The queued order completed once.",
  },
];
const slug = (cause: string) => cause.replaceAll("_", " ");

function TraceList({ trace, title }: { trace: Trace[]; title: string }) {
  return (
    <details className={styles.trace}>
      <summary>
        {title} <small>{trace.length} events</small>
      </summary>
      <ol>
        {trace.map((event, index) => (
          <li key={index}>
            <details>
              <summary>
                {event.type === "tool" ? event.name : event.model}
                {event.result?.error && (
                  <span className={styles.failure}>{event.result.error}</span>
                )}
                <small>{(event.elapsed_ms / 1000).toFixed(1)} s</small>
              </summary>
              <pre>{JSON.stringify(event, null, 2)}</pre>
            </details>
          </li>
        ))}
      </ol>
    </details>
  );
}

function Evidence({
  diagnosis,
  trace,
}: {
  diagnosis: Diagnosis;
  trace: Trace[];
}) {
  const records = new Map(
    trace
      .flatMap((event) => event.result?.records ?? [])
      .map((record) => [record.evidence_id, record]),
  );
  return (
    <ul className={styles.citations}>
      {Array.from(new Set(diagnosis.evidence_ids)).map((id) => (
        <li key={id}>
          <code>{id}</code>
          <small>
            {records.get(id)?.service ||
              slug(records.get(id)?.signal || "unobserved")}
          </small>
          <p>
            {records.get(id)?.detail ||
              "Record absent from the captured tool output."}
          </p>
        </li>
      ))}
    </ul>
  );
}

function Ratio({
  label,
  count,
  total,
  accent,
}: {
  label: string;
  count: number;
  total: number;
  accent?: boolean;
}) {
  const percent = (100 * count) / total;
  return (
    <div className={styles.ratio}>
      <div>
        <span>{label}</span>
        <strong>
          {count}/{total} <small>({percent.toFixed(1)}%)</small>
        </strong>
      </div>
      <div className={styles.track} aria-hidden="true">
        <span
          className={accent ? styles.accent : undefined}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

type BlindEvaluation = {
  byCause: {
    cause: string;
    previous: { passed: number; runs: number };
    revised: { passed: number; runs: number };
  }[];
  corrections: { previous: Failure; revised: Failure }[];
};
const causeNames: Record<string, string> = {
  db_latency: "Database latency",
  worker_stopped: "Worker stopped",
  dependency_config: "Dependency configuration",
  healthy: "Healthy",
  unknown: "Insufficient evidence",
};
const incidentName = (id: string) => id.replaceAll("-", " ");

function BlindComparison({ blind }: { blind: BlindEvaluation }) {
  const activeAnchor = useSyncExternalStore(
    subscribeToTrial,
    trialFromUrl,
    noTrial,
  );
  const total = (arm: "previous" | "revised") =>
    blind.byCause.reduce(
      (count, row) => ({
        passed: count.passed + row[arm].passed,
        runs: count.runs + row[arm].runs,
      }),
      { passed: 0, runs: 0 },
    );
  const previous = total("previous");
  const revised = total("revised");
  return (
    <section
      id="blind-evaluation"
      className={styles.section}
      aria-labelledby="blind-heading"
    >
      <div className={styles.sectionHeading}>
        <p className={styles.kicker}>Cause-label contract</p>
        <h2 id="blind-heading">Blind evaluation</h2>
        <p>
          Both prompts ran twice on 25 fresh synthetic incidents. Expected
          labels were withheld from the model.
        </p>
      </div>
      <div className={styles.panel}>
        <h3>
          {previous.passed}/{previous.runs} vs. {revised.passed}/{revised.runs}{" "}
          correct, grounded diagnoses
        </h3>
        <table className={styles.incidentTable}>
          <caption>Strict passes by expected cause</caption>
          <thead>
            <tr>
              <th scope="col">Expected cause</th>
              <th scope="col">Previous prompt</th>
              <th scope="col">Revised contract</th>
            </tr>
          </thead>
          <tbody>
            {blind.byCause.map((row) => (
              <tr key={row.cause}>
                <th scope="row">{causeNames[row.cause] ?? row.cause}</th>
                <td>
                  {row.previous.passed}/{row.previous.runs}
                </td>
                <td>
                  {row.revised.passed}/{row.revised.runs}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div id="blind-corrections" className={styles.incidentPanel}>
        <h3>{blind.corrections.length} failures corrected in paired runs</h3>
        <p>
          The previous prompt described the right mechanism in each run but
          assigned the dependency label.
        </p>
        {blind.corrections.map(({ previous, revised }) => (
          <details
            className={`${styles.panel} ${styles.blindCorrection}`}
            key={failureKey(previous)}
            id={`blind-correction-${previous.incident}-${previous.trial}`}
            open={
              activeAnchor ===
                `blind-correction-${previous.incident}-${previous.trial}` ||
              undefined
            }
          >
            <summary>
              {incidentName(previous.incident)} · Trial {previous.trial}
            </summary>
            <p>
              Expected cause <code>{previous.expected}</code>
            </p>
            <div className={styles.compareGrid}>
              {(
                [
                  [previous, "Previous prompt"],
                  [revised, "Revised contract"],
                ] as const
              ).map(([run, title]) => (
                <section
                  key={run.arm}
                  aria-label={title}
                  className={styles.blindArm}
                >
                  <h4>{title}</h4>
                  <p>
                    <code>{run.diagnosis?.cause ?? "No diagnosis"}</code> ·{" "}
                    <strong
                      className={run.strict_pass ? styles.pass : styles.failure}
                    >
                      {run.strict_pass ? "Passed grading" : "Failed grading"}
                    </strong>
                  </p>
                  {run.diagnosis && (
                    <>
                      <p>{run.diagnosis.explanation}</p>
                      <Evidence diagnosis={run.diagnosis} trace={run.trace} />
                    </>
                  )}
                  <TraceList
                    trace={run.trace}
                    title={`Inspect ${title.toLowerCase()} trace`}
                  />
                </section>
              ))}
            </div>
          </details>
        ))}
        <p>
          These results cover author-created synthetic fixtures.{" "}
          <a href="https://github.com/kilicerdal/agent-reliability-lab/blob/main/docs/blind-cause-evaluation.md">
            Read the evaluation protocol and limits
          </a>
          .
        </p>
      </div>
    </section>
  );
}

export default function Showcase({
  investigations,
  comparison,
  incidents,
  failures,
  approval,
  blind,
  recoveryComparison,
  pairedCitations,
  liveEscalation,
  handoff,
}: {
  investigations: Investigation[];
  comparison: Comparison;
  incidents: Incident[];
  failures: Failure[];
  approval: Approval;
  blind: BlindEvaluation;
  recoveryComparison: RecoveryComparison;
  pairedCitations: PairedEvidence;
  liveEscalation: EscalationEvidence;
  handoff: HandoffEvidence;
}) {
  const [scenario, setScenario] = useState("worker-failure");
  const [stage, setStage] = useState(0);
  const ready = useSyncExternalStore(
    subscribeToHydration,
    () => true,
    () => false,
  );
  const requestedTrial = useSyncExternalStore(
    subscribeToTrial,
    trialFromUrl,
    noTrial,
  );
  const failure =
    failures.find((trial) => trialId(failureKey(trial)) === requestedTrial) ??
    failures.find(
      (trial) =>
        trial.incident === "invoice-window" && trial.arm === "recovery",
    )!;
  const failedTrial = failureKey(failure);
  const selectedFailureTitle =
    failure.incident === "invoice-window" &&
    failure.diagnosis?.cause === "dependency_config"
      ? "Correct explanation, wrong cause label"
      : "Why this run failed";
  const run = investigations.find((item) => item.scenario === scenario)!;
  const snapshot = approval.states[stages[stage].key];
  const base = comparison.arms.baseline.all;
  const improved = comparison.arms.recovery.all;
  return (
    <div className={styles.viewer} id="top">
      <a className={styles.skip} href="#evidence-main">
        Skip to evidence
      </a>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <a href="#top" className={styles.brand}>
            <span aria-hidden="true">▥</span> Agent Reliability Lab
          </a>
          <nav aria-label="Evidence sections">
            <a href="#investigation">Investigation</a>
            <a href="#comparison">Evaluation</a>
            <a href="#blind-evaluation">Blind evaluation</a>
            <a href="#model-comparison">Model comparison</a>
            <a href="#paired-citations">Citation review</a>
            <a href="#live-escalation">Live escalation</a>
            <a href="#approval">Approval</a>
          </nav>
        </div>
      </header>
      <main id="evidence-main" tabIndex={-1} className={styles.main}>
        <section className={styles.hero}>
          <div>
            <p className={styles.kicker}>Recorded evidence</p>
            <h1>
              Inside an AI
              <br />
              incident investigation.
            </h1>
            <p>
              Follow the agent’s evidence, inspect a diagnosis it got wrong, and
              replay the operator approval that restored a synthetic worker.
            </p>
          </div>
          <aside
            className={styles.heroResult}
            aria-label="Held-out evaluation headline result"
          >
            <span>Correct, grounded diagnoses</span>
            <strong>
              {improved.strict_pass}
              <small> / {improved.runs}</small>
            </strong>
            <p>
              With recovery guidance · {base.strict_pass}/{base.runs} with the
              V1 prompt
            </p>
            <a href="#comparison">
              See the comparison <span aria-hidden="true">↘</span>
            </a>
          </aside>
        </section>
        <p className={styles.notice}>
          <span aria-hidden="true" /> Browsing uses recorded data and makes no
          model calls.
        </p>
        <section
          id="investigation"
          className={styles.section}
          aria-labelledby="investigation-heading"
        >
          <div className={styles.sectionHeading}>
            <p className={styles.kicker}>V1 · Investigation</p>
            <h2 id="investigation-heading">Follow the evidence</h2>
            <p>
              Four captured runs against a local PostgreSQL and HTTP workload.
            </p>
          </div>
          <div className={styles.panel}>
            <div className={styles.panelHead}>
              <div>
                <label htmlFor="case-select">Recorded case</label>
                <select
                  id="case-select"
                  disabled={!ready}
                  value={scenario}
                  onChange={(event) => setScenario(event.target.value)}
                >
                  {order
                    .filter((id) =>
                      investigations.some((item) => item.scenario === id),
                    )
                    .map((id) => (
                      <option key={id} value={id}>
                        {labels[id]}
                      </option>
                    ))}
                </select>
              </div>
              <span
                className={run.verdict.passed ? styles.pass : styles.failure}
              >
                {run.verdict.passed
                  ? "Independent checks passed"
                  : "Independent checks failed"}
              </span>
            </div>
            <div className={styles.caseGrid}>
              <div>
                <h3>{slug(run.diagnosis.cause)}</h3>
                <p>{run.diagnosis.explanation}</p>
                <small className={styles.meta}>
                  {run.usage.model} · {(run.usage.elapsed_ms / 1000).toFixed(1)}{" "}
                  s recorded
                </small>
              </div>
              <div>
                <h3>What the evaluator checked</h3>
                <ul className={styles.checks}>
                  {Object.entries(run.verdict.checks).map(([name, passed]) => (
                    <li key={name}>
                      <span
                        className={passed ? styles.pass : styles.failure}
                        aria-label={passed ? "Passed" : "Failed"}
                      >
                        {passed ? "✓" : "×"}
                      </span>
                      {slug(name)}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <h3>Cited records</h3>
            <Evidence diagnosis={run.diagnosis} trace={run.trace} />
            <TraceList trace={run.trace} title="Inspect V1 execution trace" />
          </div>
        </section>
        <section
          id="comparison"
          className={styles.section}
          aria-labelledby="comparison-heading"
        >
          <div className={styles.sectionHeading}>
            <p className={styles.kicker}>V2 · Evaluation</p>
            <h2 id="comparison-heading">What recovery guidance changed</h2>
            <p>
              {incidents.length} held-out synthetic incidents,{" "}
              {comparison.repeats} runs per incident and prompt. Both prompts
              used the same model and replayed tool fixtures.
            </p>
          </div>
          <div className={styles.compareGrid}>
            <div className={styles.panel}>
              <h3>Correct, grounded diagnosis</h3>
              <Ratio
                label="V1 prompt"
                count={base.strict_pass}
                total={base.runs}
              />
              <Ratio
                label="Recovery-guided prompt"
                count={improved.strict_pass}
                total={improved.runs}
                accent
              />
            </div>
            <div className={styles.panel}>
              <h3>Recovered after a tool failure or stale conflict</h3>
              <Ratio
                label="V1 prompt"
                count={base.recovered}
                total={base.failure_exposed}
              />
              <Ratio
                label="Recovery-guided prompt"
                count={improved.recovered}
                total={improved.failure_exposed}
                accent
              />
            </div>
          </div>
          <div className={`${styles.panel} ${styles.incidentPanel}`}>
            <h3>Results by incident</h3>
            <p>
              {
                incidents.filter((i) => i.recovery.passed > i.baseline.passed)
                  .length
              }{" "}
              improved ·{" "}
              {
                incidents.filter((i) => i.recovery.passed === i.baseline.passed)
                  .length
              }{" "}
              tied ·{" "}
              {
                incidents.filter((i) => i.recovery.passed < i.baseline.passed)
                  .length
              }{" "}
              regressed
            </p>
            <table className={styles.incidentTable}>
              <caption>Correct, grounded diagnoses per prompt</caption>
              <thead>
                <tr>
                  <th scope="col">Incident</th>
                  <th scope="col">V1 prompt</th>
                  <th scope="col">Recovery prompt</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((incident) => (
                  <tr key={incident.id}>
                    <th scope="row">
                      {incident.id.replaceAll("-", " ")}
                      <small>
                        {conditions[incident.condition] || incident.condition}
                      </small>
                    </th>
                    <td>
                      {incident.baseline.passed}/{incident.baseline.total}
                    </td>
                    <td>
                      {incident.recovery.passed}/{incident.recovery.total}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className={`${styles.panel} ${styles.failurePanel}`}>
            {failures.map((trial) => (
              <span
                key={failureKey(trial)}
                id={trialId(failureKey(trial))}
                className={styles.trialAnchor}
                aria-hidden="true"
              />
            ))}
            <div className={styles.panelHead}>
              <div>
                <label htmlFor="failure-select">Failed trial</label>
                <select
                  id="failure-select"
                  disabled={!ready}
                  value={failedTrial}
                  onChange={(event) =>
                    (window.location.hash = trialHref(event.target.value))
                  }
                >
                  {failures.map((trial) => (
                    <option key={failureKey(trial)} value={failureKey(trial)}>
                      {trial.incident.replaceAll("-", " ")} ·{" "}
                      {armLabels[trial.arm]} · Trial {trial.trial}
                    </option>
                  ))}
                </select>
              </div>
              <span className={styles.failure}>Failed grading</span>
            </div>
            <h3>{selectedFailureTitle}</h3>
            <p className={styles.trialLink}>
              <a href={trialHref(failedTrial)}>Link to this trial</a>
            </p>
            <dl className={styles.labels}>
              <div>
                <dt>Expected cause</dt>
                <dd>
                  <code>{failure.expected}</code>
                </dd>
              </div>
              <div>
                <dt>Agent returned</dt>
                <dd>
                  <code>{failure.diagnosis?.cause ?? "No diagnosis"}</code>
                </dd>
              </div>
            </dl>
            {failure.diagnosis && (
              <>
                <blockquote>{failure.diagnosis.explanation}</blockquote>
                <Evidence diagnosis={failure.diagnosis} trace={failure.trace} />
              </>
            )}
            <TraceList
              key={failedTrial}
              trace={failure.trace}
              title="Inspect V2 failure trace"
            />
          </div>
        </section>
        <BlindComparison blind={blind} />
        <ModelComparison comparison={recoveryComparison} />
        <PairedCitations
          evidence={pairedCitations}
          comparison={recoveryComparison}
        />
        <LiveEscalation evidence={liveEscalation} />
        <HandoffComparison evidence={handoff} />
        <section
          id="approval"
          className={styles.section}
          aria-labelledby="approval-heading"
        >
          <div className={styles.sectionHeading}>
            <p className={styles.kicker}>V3 · Operator approval</p>
            <h2 id="approval-heading">Replay the restart</h2>
            <p>
              Step through captured worker and order state. The test harness
              entered the confirmations through the operator command.
            </p>
          </div>
          <div className={styles.panel}>
            <ol className={styles.steps} aria-label="Recorded stages">
              {stages.map((item, index) => (
                <li key={item.key}>
                  <button
                    type="button"
                    disabled={!ready}
                    aria-pressed={stage === index}
                    aria-controls="replay-state"
                    onClick={() => setStage(index)}
                  >
                    <span aria-hidden="true">{index + 1}</span>
                    {item.title}
                  </button>
                </li>
              ))}
            </ol>
            <div
              id="replay-state"
              aria-live="polite"
              aria-atomic="true"
              className={styles.snapshot}
            >
              <h3>{stages[stage].title}</h3>
              <p>{stages[stage].detail}</p>
              <dl>
                <div>
                  <dt>Worker</dt>
                  <dd>{snapshot.worker_enabled ? "Enabled" : "Disabled"}</dd>
                </div>
                <div>
                  <dt>Order</dt>
                  <dd>{snapshot.order_status}</dd>
                </div>
                <div>
                  <dt>Restart events</dt>
                  <dd>{snapshot.restart_events}</dd>
                </div>
                <div>
                  <dt>Completion events</dt>
                  <dd>{snapshot.completion_events}</dd>
                </div>
              </dl>
            </div>
            <details className={styles.trace}>
              <summary>Inspect MCP and database checks</summary>
              <dl className={styles.boundaries}>
                <div>
                  <dt>MCP protocol</dt>
                  <dd>{approval.protocol}</dd>
                </div>
                <div>
                  <dt>Out-of-contract MCP calls denied</dt>
                  <dd>
                    {
                      Object.values(approval.denied_mcp_calls).filter(Boolean)
                        .length
                    }
                  </dd>
                </div>
                <div>
                  <dt>Prohibited SQL updates</dt>
                  <dd>
                    {Object.entries(approval.denied_database_sqlstates).map(
                      ([key, status]) => (
                        <span key={key}>
                          {slug(key)} <code>{status}</code>
                        </span>
                      ),
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Concurrent approval results</dt>
                  <dd>{approval.concurrent_results.join(", ")}</dd>
                </div>
                <div>
                  <dt>Stale request result</dt>
                  <dd>{approval.expired_result}</dd>
                </div>
              </dl>
            </details>
          </div>
        </section>
        <section
          className={styles.downloads}
          aria-labelledby="download-heading"
        >
          <h2 id="download-heading">Download the evidence</h2>
          <div>
            <a
              download
              href={`${process.env.NEXT_PUBLIC_LAB_BASE_PATH || ""}/recordings/v1-captures.json`}
            >
              V1 captures · JSON ↓
            </a>
            <a
              download
              href={`${process.env.NEXT_PUBLIC_LAB_BASE_PATH || ""}/recordings/v2-scorecard.json`}
            >
              V2 scorecard · JSON ↓
            </a>
            <a
              download
              href={`${process.env.NEXT_PUBLIC_LAB_BASE_PATH || ""}/recordings/v2-traces.jsonl`}
            >
              V2 traces · JSONL ↓
            </a>
            <a
              download
              href={`${process.env.NEXT_PUBLIC_LAB_BASE_PATH || ""}/recordings/v3-approval.json`}
            >
              V3 approval · JSON ↓
            </a>
            <a
              download
              href={`${process.env.NEXT_PUBLIC_LAB_BASE_PATH || ""}/recordings/v3-prompt-trials.jsonl`}
            >
              V3 prompt trials · JSONL ↓
            </a>
            <a
              download
              href={`${process.env.NEXT_PUBLIC_LAB_BASE_PATH || ""}/recordings/blind-scorecard.json`}
            >
              Blind scorecard · JSON ↓
            </a>
            <a
              download
              href={`${process.env.NEXT_PUBLIC_LAB_BASE_PATH || ""}/recordings/blind-traces.jsonl`}
            >
              Blind trials · JSONL ↓
            </a>
            <a
              download
              href={`${process.env.NEXT_PUBLIC_LAB_BASE_PATH || ""}/recordings/model-comparison.json`}
            >
              Model comparison · JSON ↓
            </a>
            <a
              download
              href={`${process.env.NEXT_PUBLIC_LAB_BASE_PATH || ""}/recordings/model-comparison-traces.jsonl`}
            >
              Recovery traces · JSONL ↓
            </a>
            <a
              download
              href={`${process.env.NEXT_PUBLIC_LAB_BASE_PATH || ""}/recordings/scoped-approval.json`}
            >
              Database approval evidence · JSON ↓
            </a>
          </div>
          <p>
            V1 uses development cases. V2 uses held-out replay fixtures. V3 uses
            one synthetic worker incident. The results describe the recorded
            scenarios.
          </p>
        </section>
      </main>
      <footer className={styles.footer}>
        <span>Agent Reliability Lab · Erdal Kilic</span>
        <a href="https://github.com/kilicerdal/agent-reliability-lab">
          Source on GitHub ↗
        </a>
      </footer>
    </div>
  );
}
