"use client";
import { useEffect, useState } from "react";
type RecordItem = {
  evidence_id: string;
  service: string;
  signal: string;
  detail: string;
};
type Trace = {
  type: string;
  step?: number;
  name?: string;
  ok?: boolean;
  model?: string;
  input_tokens?: number;
  output_tokens?: number;
  estimated_usd?: number;
  elapsed_ms: number;
  result?: { records?: RecordItem[]; queued?: number; orders?: unknown[] };
};
type Run = {
  id: string;
  recorded_at: string;
  scenario: string;
  mode: string;
  scope: string;
  diagnosis: {
    cause: string;
    explanation: string;
    evidence_ids: string[];
    alternative: string;
    next_check: string;
  };
  trace: Trace[];
  usage: { estimated_usd: number; elapsed_ms: number; model: string };
  verdict: {
    passed: boolean;
    checks: Record<string, boolean>;
    expected_cause: string;
    limitation: string;
  };
};
const labels: Record<string, string> = {
  "database-slowdown": "Database slowdown",
  "worker-failure": "Worker unavailable",
  "dependency-failure": "Dependency failure",
  healthy: "Healthy control",
};
export default function Page() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/lab/runs");
      if (!res.ok)
        throw Error(
          "Capture service is unavailable. Start the backend and try again.",
        );
      const data = await res.json();
      setRuns(data);
      setSelected((old) =>
        data.some((r: Run) => r.id === old) ? old : data[0]?.id || "",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load captures.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);
  const run = runs.find((r) => r.id === selected);
  const pass = runs.filter((r) => r.verdict.passed).length;
  const traces = run?.trace.filter((t) => t.type === "tool") || [];
  const records = Array.from(
    new Map(
      traces
        .flatMap((t) => t.result?.records || [])
        .map((r) => [r.evidence_id, r]),
    ).values(),
  );
  return (
    <>
      <a className="skip" href="#workspace">
        Skip to investigation
      </a>
      <header>
        <a href="/" className="brand">
          <span className="mark">▥</span> Agent Reliability Lab
        </a>
        <span className="release">V1 · INCIDENT INVESTIGATOR</span>
      </header>
      <main>
        <section className="hero">
          <p className="eyebrow">SYNTHETIC INCIDENTS. OBSERVABLE DECISIONS.</p>
          <h1>
            Evidence before
            <br />
            <span>confidence.</span>
          </h1>
          <p className="intro">
            An AI investigator follows the signals. A separate evaluator checks
            whether it reached the right conclusion—and left the system
            untouched.
          </p>
          <div className="chips">
            <span>Read-only tools</span>
            <span>Real local PostgreSQL</span>
            <span>Independent oracle</span>
          </div>
        </section>
        <section className="metrics" aria-label="Captured evaluation summary">
          <div>
            <small>CAPTURED INVESTIGATIONS</small>
            <strong>{runs.length}</strong>
          </div>
          <div>
            <small>PASSED ALL CHECKS</small>
            <strong>
              {pass}
              <em> / {runs.length}</em>
            </strong>
          </div>
          <div>
            <small>MODEL USAGE ESTIMATE</small>
            <strong>
              ${runs.reduce((n, r) => n + r.usage.estimated_usd, 0).toFixed(4)}
            </strong>
          </div>
          <div>
            <small>DEMONSTRATION SCOPE</small>
            <strong className="small-value">Development cases</strong>
          </div>
        </section>
        <div className="notice">
          <span className="dot" /> Recorded evidence viewer. Browsing this
          dashboard makes no model calls. These small development samples are
          not a production accuracy benchmark.
        </div>
        <section id="workspace" tabIndex={-1} className="workspace">
          <aside>
            <p className="eyebrow">INVESTIGATION ARCHIVE</p>
            <h2>Choose a capture</h2>
            <button
              className="refresh"
              onClick={() => void refresh()}
              disabled={loading}
            >
              {loading ? "Loading…" : "Refresh captures"}
            </button>
            {error && <p role="alert">{error}</p>}
            {!loading && !error && !runs.length && (
              <p>
                No captured run yet. Run a local investigation using the README
                commands.
              </p>
            )}
            <div className="run-list">
              {runs.map((r) => (
                <button
                  key={r.id}
                  aria-pressed={selected === r.id}
                  onClick={() => setSelected(r.id)}
                >
                  <span
                    className={r.verdict.passed ? "status pass" : "status fail"}
                  >
                    {r.verdict.passed ? "PASS" : "FAIL"}
                  </span>
                  <strong>{labels[r.scenario] || r.scenario}</strong>
                  <small>
                    {new Date(r.recorded_at).toLocaleString()} ·{" "}
                    {r.id.slice(0, 8)}
                  </small>
                </button>
              ))}
            </div>
          </aside>
          {run ? (
            <article className="case" aria-label="Selected investigation">
              <div className="case-head">
                <div>
                  <p className="eyebrow">CASE FILE / {run.id.slice(0, 8)}</p>
                  <h2>{labels[run.scenario] || run.scenario}</h2>
                </div>
                <span
                  className={
                    run.verdict.passed ? "verdict pass" : "verdict fail"
                  }
                >
                  {run.verdict.passed ? "Verified outcome" : "Checks failed"}
                </span>
              </div>
              <p className="meta">
                {run.usage.model} · {(run.usage.elapsed_ms / 1000).toFixed(1)}s
                · ${run.usage.estimated_usd.toFixed(4)} estimated · {run.mode}
              </p>
              <section className="diagnosis">
                <p className="eyebrow">INVESTIGATOR’S CONCLUSION</p>
                <h3>{run.diagnosis.cause.replaceAll("_", " ")}</h3>
                <p>{run.diagnosis.explanation}</p>
                <dl>
                  <dt>Alternative considered</dt>
                  <dd>{run.diagnosis.alternative}</dd>
                  <dt>Recommended next check</dt>
                  <dd>{run.diagnosis.next_check}</dd>
                </dl>
              </section>
              <section>
                <h3>Independent verdict</h3>
                <p className="muted">
                  Expected cause: <code>{run.verdict.expected_cause}</code>. The
                  oracle is not provided to the investigator.
                </p>
                <ul className="checks">
                  {Object.entries(run.verdict.checks).map(([k, v]) => (
                    <li key={k}>
                      <span className={v ? "pass" : "fail"}>
                        {v ? "✓" : "×"}
                      </span>
                      {k.replaceAll("_", " ")}
                    </li>
                  ))}
                </ul>
                <p className="fine">{run.verdict.limitation}</p>
              </section>
              <section>
                <h3>Cited evidence</h3>
                <div className="evidence">
                  {run.diagnosis.evidence_ids.map((id) => {
                    const record = records.find((r) => r.evidence_id === id);
                    return (
                      <div key={id}>
                        <code>{id}</code>
                        <span>{record?.service || "Not observed"}</span>
                        <p>
                          {record?.detail ||
                            "Citation does not exist in observed tool output."}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </section>
              <section>
                <h3>Execution trace</h3>
                <p className="muted">
                  Recorded tool inputs and outputs. No private reasoning is
                  displayed.
                </p>
                <ol className="timeline">
                  {run.trace.map((t, i) => (
                    <li key={i}>
                      <details>
                        <summary>
                          <span>{t.type === "model" ? "MODEL" : "TOOL"}</span>{" "}
                          {t.type === "model"
                            ? `${t.model} · ${t.input_tokens} in / ${t.output_tokens} out`
                            : t.name}
                          <small>{(t.elapsed_ms / 1000).toFixed(1)}s</small>
                        </summary>
                        <pre>{JSON.stringify(t, null, 2)}</pre>
                      </details>
                    </li>
                  ))}
                </ol>
              </section>
              <details className="raw">
                <summary>Complete capture JSON</summary>
                <pre>{JSON.stringify(run, null, 2)}</pre>
              </details>
              <p className="fine">{run.scope}</p>
            </article>
          ) : (
            <article className="case empty">
              <h2>
                {loading ? "Loading evidence…" : "No investigation selected"}
              </h2>
              <p>
                Select a recorded capture to inspect the diagnosis, tool calls
                and verdict.
              </p>
            </article>
          )}
        </section>
        <section className="method">
          <p className="eyebrow">HOW TO READ A GREEN RESULT</p>
          <h2>A passing check has boundaries.</h2>
          <div>
            <p>
              <b>Real faults.</b> The harness executes a delayed SQL query,
              stops a synthetic worker, or changes an HTTP dependency setting.
            </p>
            <p>
              <b>Separate judgment.</b> Deterministic checks compare the
              diagnosis with the injected cause, verify observed citations and
              compare workload fingerprints.
            </p>
            <p>
              <b>Explicit limits.</b> V1 does not measure production readiness,
              prove every sentence, or authorize remediation. No employer or
              customer data is used.
            </p>
          </div>
        </section>
      </main>
      <footer>
        <span>Built by Erdal Kilic · Synthetic engineering demonstration</span>
        <span>Local evaluation · Recorded results · V1</span>
      </footer>
    </>
  );
}
