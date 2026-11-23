import json
import time

from backend.lab.agent import MODEL, PROMPT
from backend.lab.contracts import Diagnosis
from backend.lab.tools import TOOLS

RECOVERY = """ If a tool reports a retryable timeout, retry that tool once. If a source is unavailable, use other read tools and their independent observations. Prefer current direct measurements to stale summaries, and cite corroboration from both workload and configuration when available. If essential evidence is absent or current credible observations still conflict, choose unknown and cite what limits your conclusion."""


CAUSE_GUIDE = {
    "db_latency": "The database query path causes the delay, including a configured SQL delay.",
    "worker_stopped": "The fulfillment worker is stopped or disabled, leaving work queued.",
    "dependency_config": "An external service dependency is misconfigured, such as an inventory route.",
    "healthy": "Current observations support normal operation.",
    "unknown": "Available evidence does not establish which cause applies.",
}
CAUSE_CONTRACT = (
    " Before returning the diagnosis, match the causal subsystem in your explanation "
    "to the exact cause label in the schema. Choose the label for the mechanism "
    "that explains the observations. A configuration change can affect any subsystem."
)


def investigate(
    alert,
    dispatch,
    client,
    budget,
    *,
    improved,
    trace,
    tools=TOOLS,
    instructions=PROMPT,
    cause_contract=True,
):
    schema = Diagnosis.model_json_schema()
    if cause_contract:
        schema["properties"]["cause"]["description"] = " ".join(
            f"{label}: {meaning}" for label, meaning in CAUSE_GUIDE.items()
        )
        instructions += CAUSE_CONTRACT
    messages = [{"role": "user", "content": alert}]
    start = time.monotonic()
    total = 0
    for step in range(8):
        payload = {
            "model": MODEL,
            "instructions": instructions + (RECOVERY if improved else ""),
            "input": messages,
            "tools": tools,
            "parallel_tool_calls": False,
            "max_output_tokens": 4096,
            "reasoning": {"effort": "low"},
            "store": False,
            "service_tier": "default",
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "diagnosis",
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        if len(json.dumps(payload).encode()) > 80000:
            raise ValueError("Investigation context limit reached")
        rid = budget.reserve()
        # Failed/uncertain calls retain reservation; automatic SDK retries are disabled.
        response = client.responses.create(**payload)
        usage = response.usage
        if usage is None:
            raise RuntimeError("Usage missing: request remains reserved")
        cost = budget.settle(rid, usage.input_tokens, usage.output_tokens)
        total += cost
        trace.append(
            {
                "type": "model",
                "step": step,
                "response_id": response.id,
                "model": response.model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "estimated_usd": cost,
                "elapsed_ms": round((time.monotonic() - start) * 1000),
            }
        )
        messages.extend(o.model_dump(exclude_none=True) for o in response.output)
        calls = [o for o in response.output if o.type == "function_call"]
        if not calls:
            diagnosis = Diagnosis.model_validate_json(response.output_text)
            return (
                diagnosis,
                trace,
                {
                    "estimated_usd": round(total, 6),
                    "elapsed_ms": round((time.monotonic() - start) * 1000),
                    "model": MODEL,
                },
            )
        for call in calls:
            try:
                args = json.loads(call.arguments)
                result = dispatch(call.name, args)
                ok = True
            except (ValueError, TypeError):
                result = {"error": "Tool or arguments denied"}
                ok = False
            trace.append(
                {
                    "type": "tool",
                    "name": call.name,
                    "arguments": call.arguments,
                    "ok": ok,
                    "result": result,
                    "elapsed_ms": round((time.monotonic() - start) * 1000),
                }
            )
            messages.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                }
            )
    raise RuntimeError("Investigation step limit reached")
