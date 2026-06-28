"""Agent Card definitions for the two A2A services.

A single source of truth imported by both the service that mounts the card
(for the /.well-known/agent.json endpoint) and any client that wants to
describe or log the remote agent's capabilities.
"""

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill


def researcher_card(url: str) -> AgentCard:
    return AgentCard(
        name="Researcher Agent",
        description=(
            "Performs web search and page retrieval, then produces a cited "
            "research summary for a given query."
        ),
        version="1.0.0",
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=url)],
        skills=[
            AgentSkill(
                id="research",
                name="Research",
                description="Web search + page retrieval + cited summarisation.",
                input_modes=["application/json"],
                output_modes=["application/json"],
                tags=["research", "web-search", "summarisation"],
                examples=["What are the main LLM observability tools in 2026?"],
            )
        ],
    )


def evaluator_card(url: str) -> AgentCard:
    return AgentCard(
        name="Evaluator Agent",
        description=(
            "LLM-as-judge: scores a ResearchResult for faithfulness, "
            "completeness, and guardrail compliance."
        ),
        version="1.0.0",
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=url)],
        skills=[
            AgentSkill(
                id="evaluate",
                name="Evaluate",
                description="Scores a research summary against the original query on three dimensions.",
                input_modes=["application/json"],
                output_modes=["application/json"],
                tags=["evaluation", "llm-as-judge", "faithfulness"],
                examples=["Score: {query: '...', research: {summary: '...', sources: [...]}}"],
            )
        ],
    )
