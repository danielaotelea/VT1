"""Gradio chat UI — calls the Multi-Agent Research FastAPI backend."""

import httpx
import gradio as gr

BACKEND_URL = "http://localhost:8001"

EXPORTERS = ["langfuse", "phoenix", "opik", "otel-stdout", "none"]

EXAMPLES = [
    ["What are the main observability tools for LLM agents in 2025?"],
    ["How does LangSmith compare to Langfuse for LLM tracing?"],
    ["What is OpenTelemetry and how is it used in AI systems?"],
    ["What are best practices for monitoring multi-agent AI pipelines?"],
    ["How does Arize Phoenix support LLM evaluation?"],
    ["What is the difference between tracing and logging in AI observability?"],
]

_current_exporter: dict[str, str] = {"value": "none"}


def activate_exporter(exporter: str) -> str:
    _current_exporter["value"] = exporter
    try:
        r = httpx.post(f"{BACKEND_URL}/exporter/{exporter}", timeout=10)
        r.raise_for_status()
        data = r.json()
        status = "active" if data["active"] else "failed to initialise"
        return f"Exporter: {data['exporter']} — {status} ({data['collector_url']})"
    except Exception as e:
        return f"Could not activate exporter: {e}"


def chat(message: str, _history: list[dict]) -> str:
    exporter = _current_exporter["value"]
    response = httpx.post(
        f"{BACKEND_URL}/chat",
        json={"query": message, "exporter": exporter},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()

    hitl_warning = "\n\n⚠️ **HITL escalation required** — confidence too low after retries." if data["hitl_required"] else ""
    scores = (
        f"\n\n---\n"
        f"**Evaluation** | faithfulness: `{data['faithfulness']:.2f}` | "
        f"completeness: `{data['completeness']:.2f}` | "
        f"label: `{data['label']}` | "
        f"retries: `{data['retry_count']}`"
    )
    return data["final_answer"] + scores + hitl_warning


with gr.Blocks(title="Multi-Agent Research") as demo:
    gr.Markdown("## Multi-Agent Research & Fact-Check\nResearch queries answered by Researcher → Evaluator → Orchestrator pipeline.")

    with gr.Row():
        exporter_dd = gr.Dropdown(
            choices=EXPORTERS,
            value="none",
            label="Tracing exporter",
            interactive=True,
            scale=2,
        )
        exporter_status = gr.Textbox(
            label="Exporter status",
            interactive=False,
            scale=3,
        )

    exporter_dd.change(fn=activate_exporter, inputs=exporter_dd, outputs=exporter_status)

    chat_interface = gr.ChatInterface(fn=chat)

    gr.Markdown("### Example questions")
    example_table = gr.Dataset(
        components=[gr.Textbox(visible=False)],
        samples=EXAMPLES,
        headers=["Click a question to load it into the chat"],
        type="index",
    )

    example_table.click(
        fn=lambda idx: EXAMPLES[idx][0],
        inputs=example_table,
        outputs=chat_interface.textbox,
    )

if __name__ == "__main__":
    demo.launch(server_port=7861)
