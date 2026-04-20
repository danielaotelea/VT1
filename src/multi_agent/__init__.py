"""Multi-agent Research & Fact-Check system.

Three-agent pipeline:
  OrchestratorAgent → ResearcherAgent → EvaluatorAgent

Quick start::

    from src.multi_agent.orchestrator import run
    print(run("What are the main observability tools for LLM agents in 2025?"))
"""

from .config import MultiAgentConfig
from .evaluator import EvaluatorAgent
from .orchestrator import LoopDetectedError, OrchestratorAgent, PIIExposureError, run
from .researcher import ResearcherAgent
from .state import AgentState, EvaluationResult, ResearchResult, TraceEvent

__all__ = [
    "MultiAgentConfig",
    "AgentState",
    "TraceEvent",
    "ResearchResult",
    "EvaluationResult",
    "ResearcherAgent",
    "EvaluatorAgent",
    "OrchestratorAgent",
    "LoopDetectedError",
    "PIIExposureError",
    "run",
]
