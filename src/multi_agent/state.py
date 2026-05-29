"""Shared state schema for the multi-agent Research & Fact-Check system.

All three agents (Orchestrator, Researcher, Evaluator) communicate exclusively
through AgentState, which is passed through the LangGraph StateGraph.

trace_events uses operator.add so each node appends rather than overwrites —
the full multi-agent audit trail accumulates automatically across graph nodes.
messages uses LangGraph's add_messages reducer for the same reason.
All other fields are plain values; nodes return only the keys they modify.
"""

import operator
from datetime import datetime, timezone
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph import add_messages


class TraceEvent(TypedDict):
    """A single structured event emitted by any agent during a run."""
    timestamp: str      # ISO-8601
    agent: str          # "orchestrator" | "researcher" | "evaluator"
    event_type: str     # "tool_call" | "llm_response" | "guard_triggered" | "evaluation"
    payload: dict       # event-specific data


class ResearchResult(TypedDict):
    """Output produced by ResearcherAgent."""
    summary: str
    sources: list       # each: {"url": str, "excerpt": str}


class EvaluationResult(TypedDict):
    """Scores produced by EvaluatorAgent."""
    faithfulness: float
    completeness: float
    guardrail_compliance: float
    label: str          # "grounded" | "hallucinated"
    raw_response: str


def make_event(agent: str, event_type: str, payload: dict) -> TraceEvent:
    """Create a TraceEvent stamped with the current UTC time."""
    return TraceEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        agent=agent,
        event_type=event_type,
        payload=payload,
    )


class AgentState(TypedDict):
    """Shared state passed through the LangGraph StateGraph.

    Fields with reducers (messages, trace_events) are append-only — nodes return
    lists that get merged into the accumulated state automatically.
    All other fields are replaced by whatever the node returns for that key.
    """
    query: str                                           # original user query, set once at run() entry
    messages: Annotated[list[Any], add_messages]         # conversation thread
    trace_events: Annotated[list, operator.add]          # append-only audit trail across all agents
    research: ResearchResult
    evaluation: EvaluationResult
    retry_count: int
    hitl_required: bool
    final_answer: str
    query_counts: dict                                   # loop detection: {query_text: call_count}
    conversation_history: list                           # prior-turn messages for multi-turn synthesis
