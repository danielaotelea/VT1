"""Typed loader for multi-agent prompt templates.

Prompts live in prompts.yml next to this file.  Edit YAML to change prompt
text; the Python code that uses PROMPTS never needs to touch.

PROMPTS is a module-level singleton loaded once at import — any YAML error
surfaces immediately at startup rather than at the first LLM call.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class MultiAgentPrompts:
    researcher_system: str
    evaluator_system: str
    evaluator_judge: str          # string.Template: $query, $summary, $sources
    orchestrator_synthesis: str


def _load() -> MultiAgentPrompts:
    data = yaml.safe_load((Path(__file__).parent / "prompts.yml").read_text(encoding="utf-8"))
    return MultiAgentPrompts(
        researcher_system=data["researcher"]["system"].strip(),
        evaluator_system=data["evaluator"]["system"].strip(),
        evaluator_judge=data["evaluator"]["judge"],
        orchestrator_synthesis=data["orchestrator"]["synthesis"].strip(),
    )


PROMPTS: MultiAgentPrompts = _load()
