import os
from dataclasses import dataclass, field

from src.multi_agent.config import MultiAgentConfig


@dataclass
class MultiAgentA2AConfig(MultiAgentConfig):
    """Extends MultiAgentConfig with A2A service URLs and ports.

    Researcher and Evaluator are deployed as standalone A2A services;
    the Orchestrator calls them over HTTP instead of in-process.
    """
    researcher_url: str = field(default_factory=lambda: os.getenv("RESEARCHER_URL", "http://127.0.0.1:8011"))
    evaluator_url: str = field(default_factory=lambda: os.getenv("EVALUATOR_URL", "http://127.0.0.1:8012"))
    researcher_port: int = 8011
    evaluator_port: int = 8012

    # A2A-specific project names — override the multi_agent defaults
    phoenix_project_name: str = field(default_factory=lambda: os.getenv("PHOENIX_PROJECT_NAME_A2A", "vt1-a2a"))
    opik_project_name: str = field(default_factory=lambda: os.getenv("OPIK_PROJECT_NAME_A2A", "vt1-a2a"))
    langfuse_public_key: str = field(default_factory=lambda: os.getenv("LANGFUSE_PUBLIC_KEY_A2A", ""))
    langfuse_secret_key: str = field(default_factory=lambda: os.getenv("LANGFUSE_SECRET_KEY_A2A", ""))
