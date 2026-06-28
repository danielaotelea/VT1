"""Async transport helper for the A2A v2 orchestrator.

call_agent() sends a structured JSON payload to an A2A service and returns
the result dict plus the trace events the service emitted — mirroring the
(result, events) tuple returned by ResearcherAgent.run() / EvaluatorAgent.run()
in the in-process v1 system.

Distributed tracing headers are built by the orchestrator via its active
TracingStrategy.outgoing_headers() and passed in as the *headers* argument.
The strategy is the single source of truth for which headers to inject and how
— this function is transport-only and knows nothing about observability tools.
"""

import logging
from typing import Any

import httpx

from a2a.client import ClientConfig, create_client
from a2a.helpers import get_data_parts, new_data_message
from a2a.types import Role, SendMessageRequest, TaskState

from src.multi_agent.state import TraceEvent

log = logging.getLogger("multi_agent_a2a.protocol")


async def call_agent(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> tuple[dict, list[TraceEvent]]:
    """Send *payload* to the A2A service at *url* and return its structured response.

    *headers* should contain the distributed-tracing headers produced by the
    orchestrator's TracingStrategy.outgoing_headers().  Pass an empty dict or
    None when tracing is disabled.

    Raises RuntimeError if the task fails, returns no artifacts, or the
    stream ends without a completed task.
    """
    log.debug(f"call_agent → {url}  payload_keys={list(payload.keys())} headers={list((headers or {}).keys())}")

    http = httpx.AsyncClient(headers=headers or {}, timeout=120.0)
    client = await create_client(agent=url, client_config=ClientConfig(streaming=False, httpx_client=http))
    try:
        message = new_data_message(data=payload, role=Role.ROLE_USER)
        request = SendMessageRequest(message=message)
        async for chunk in client.send_message(request):
            if chunk.HasField("task"):
                task = chunk.task
                if task.status.state == TaskState.TASK_STATE_FAILED:
                    raise RuntimeError(f"A2A agent at {url} reported TASK_STATE_FAILED.")
                if task.status.state == TaskState.TASK_STATE_COMPLETED:
                    if not task.artifacts:
                        raise RuntimeError(f"A2A agent at {url} completed with no artifacts.")
                    data = get_data_parts(task.artifacts[0].parts)[0]
                    result: dict = data.get("result", {})
                    events: list[TraceEvent] = data.get("trace_events", [])
                    log.debug(f"call_agent ← {url}  result_keys={list(result.keys())} events={len(events)}")
                    return result, events
    finally:
        await client.close()
        await http.aclose()
    raise RuntimeError(f"A2A agent at {url} stream ended without a completed task.")
