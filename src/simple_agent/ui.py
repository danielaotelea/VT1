"""Gradio chat UI — calls the SimpleAgent FastAPI backend."""

import httpx
import gradio as gr

BACKEND_URL = "http://localhost:8000"

EXPORTERS = ["langfuse", "phoenix", "opik", "otel-stdout", "none"]

EXAMPLES = [
    "What is 6 multiplied by 7?",
    "What is 123 plus 456?",
    "Divide 100 by 4, then add 13.",
    "Multiply 8 by 9, then divide the result by 6.",
    "What is 15 divided by 3?",
    "Add 27 and 73, then multiply by 2.",
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
        json={"message": message, "exporter": exporter},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["response"]


with gr.Blocks(title="Simple Agent") as demo:
    gr.Markdown("## Simple Agent\nArithmetic agent with pluggable observability tracing.")

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

    gr.ChatInterface(fn=chat, examples=EXAMPLES)

if __name__ == "__main__":
    demo.launch()
