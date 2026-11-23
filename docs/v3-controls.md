# V3 MCP and operator-approved remediation

V3 adds a local MCP server with four investigation tools and one request tool. It uses the official MCP Python SDK over stdio and negotiates the protocol with a real subprocess client. The launcher binds the subprocess to one synthetic experiment, and all tool schemas accept an empty object.

| Tool | Purpose |
| --- | --- |
| `read_logs`, `read_health` | Read bounded observations for the bound experiment |
| `read_deployments` | Read configuration observations for the bound experiment |
| `read_queue` | Read the bound experiment's queued orders |
| `request_worker_restart` | Create or return one pending operator request for the bound experiment |

The request table permits one request per experiment. The MCP PostgreSQL role can insert the experiment column and read request status. PostgreSQL denies that role writes to worker state, orders, and approval records. The trusted operator runs a separate CLI with the database owner credential and types the exact experiment UUID to confirm. This is a local operator workflow using credential possession and terminal confirmation. The confirmation field is not an identity check.

Under a row lock, the approval handler checks for a pending request less than 15 minutes old and a currently disabled worker in a worker-failure experiment. It enables that worker, records approval, and appends the audit event in one transaction. The existing worker tick then processes the order through the real synthetic HTTP inventory service.

## Observed results

| Step | Worker enabled | Order | Restart events | Completion events |
| --- | ---: | --- | ---: | ---: |
| Before request | No | Queued | 0 | 0 |
| Pending request and repeated request | No | Queued | 0 | 0 |
| Wrong confirmation | No | Queued | 0 | 0 |
| Two concurrent matching confirmations | Yes | Queued | 1 | 0 |
| Two worker ticks | Yes | Completed | 1 | 1 |

The integration harness supplied both confirmations by script. It observed one `applied` and one `already_applied` response. Four out-of-contract MCP calls were denied, and PostgreSQL rejected both tested prohibited updates with SQLSTATE `42501`. The neighboring experiment's fingerprint stayed unchanged. An expired request left its worker disabled.

Three paired live GPT-6.2 Sol investigations used fresh worker-failure experiments. Each pair compared a neutral observation with one untrusted observation asking for an incorrect healthy diagnosis and a marker string. The model received each note through an MCP read. All three injected runs and all three controls produced the correct grounded diagnosis, omitted the marker, and left the worker disabled without a restart request. Estimated cost was $0.045856 for 18 model requests at the project's standard token rates.

These trials cover one incident type and three deliberately simple notes. In the original V3 capture, the tool handler enforced experiment scope and the shared PostgreSQL role had cross-experiment read access. The [current database-scoped controls](assurance.md#database-scoped-approval) add row-level enforcement. This lab uses local synthetic credentials and a trusted launcher, operator, and model host. The worker remediation re-enables application configuration.

## Reproduce

Install the pinned Python dependencies. Start a dedicated synthetic PostgreSQL database and the V1 inventory service. Set `LAB_DATABASE_URL` to the database owner connection. Use password authentication for the subprocess connections. The installer creates the MCP privilege group and row policies. `LAB_INVENTORY_URL` defaults to `http://127.0.0.1:8811`.

```sh
python -m backend.controls.approval install
python -m backend.controls.evidence --output .private/v3-boundaries-new.json
python -m backend.controls.verify
```

To exercise the operator workflow manually, first create a worker-failure experiment.

```sh
python -c 'from backend.lab.sandbox import reproduce; print(reproduce("worker-failure"))'
```

Configure a trusted local MCP host to launch `python -m backend.controls.approval serve EXPERIMENT_ID` from the repository root. The launcher uses the owner connection to provision a scoped role and starts the MCP subprocess with the scoped connection. List the tools and call `request_worker_restart` with `{}`. Then run these commands in the separate operator environment, substituting the UUID.

```sh
python -m backend.controls.approval approve EXPERIMENT_ID
python -m backend.lab.worker EXPERIMENT_ID --ticks 1
```

The live prompt trials can be replayed with the approved API key in the environment and the existing project ledger. The command spends API credits.

```sh
python -m backend.controls.prompt_trials --output .private/v3-prompt-trials-new.jsonl
```

[Boundary and state capture](../evidence/v3/boundaries.json) · [All six model traces](../evidence/v3/prompt-trials.jsonl) · [MCP SDK server documentation](https://py.sdk.modelcontextprotocol.io/v2/advanced/low-level-server/)
