"""Typed loader for simple-agent prompt templates.

Prompts live in prompts.yml next to this file.  Edit YAML to change prompt
text; the agent code never needs to touch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SimpleAgentPrompts:
    system: str


def _load() -> SimpleAgentPrompts:
    data = yaml.safe_load((Path(__file__).parent / "prompts.yml").read_text(encoding="utf-8"))
    return SimpleAgentPrompts(system=data["simple_agent"]["system"].strip())


PROMPTS: SimpleAgentPrompts = _load()
