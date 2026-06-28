"""Gradio chat UI — calls the Multi-Agent Research FastAPI backend."""

import httpx

from src.ui import build_demo

BACKEND_URL = "http://localhost:8001"

EXAMPLES = [
    ["What are the main observability tools for LLM agents in 2025?"],
    ["How does LangSmith compare to Langfuse for LLM tracing?"],
    ["What is OpenTelemetry and how is it used in AI systems?"],
    ["What are best practices for monitoring multi-agent AI pipelines?"],
    ["How does Arize Phoenix support LLM evaluation?"],
    ["What is the difference between tracing and logging in AI observability?"],
]


def chat(message: str, _history: list, exporter: str, session_id: str) -> str:
    response = httpx.post(
        f"{BACKEND_URL}/chat",
        json={"query": message, "exporter": exporter, "session_id": session_id},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()

    hitl_warning = (
        "\n\n⚠️ **HITL escalation required** — confidence too low after retries."
        if data["hitl_required"] else ""
    )
    scores = (
        f"\n\n---\n"
        f"**Evaluation** | faithfulness: `{data['faithfulness']:.2f}` | "
        f"completeness: `{data['completeness']:.2f}` | "
        f"label: `{data['label']}` | "
        f"retries: `{data['retry_count']}`"
    )
    return data["final_answer"] + scores + hitl_warning


demo = build_demo(
    backend_url=BACKEND_URL,
    title="Multi-Agent Research",
    description="Research queries answered by Researcher → Evaluator → Orchestrator pipeline.",
    examples=EXAMPLES,
    chat_fn=chat,
)

if __name__ == "__main__":
    demo.launch()
