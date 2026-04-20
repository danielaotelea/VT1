"""Shared state schema for the multi-agent Research & Fact-Check system.

All three agents (Orchestrator, Researcher, Evaluator) communicate exclusively
through AgentState, which is passed through the LangGraph graph as a TypedDict.
trace_events is the coordination audit trail — every agent appends structured
events so the Orchestrator can detect failures and the observability platform
can reconstruct the full multi-agent trace.
"""

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


class AgentState(TypedDict):
    """Shared state passed between all agents in the LangGraph graph.

    messages uses add_messages so each agent can append without overwriting.
    research and evaluation hold the latest outputs from their respective agents.
    hitl_required is set to True by the Orchestrator when confidence stays low
    after max_evaluator_retries exhausted.
    """
    messages: Annotated[list[Any], add_messages]
    trace_events: list
    research: ResearchResult
    evaluation: EvaluationResult
    retry_count: int
    hitl_required: bool
    final_answer: str
