"""Gradio chat UI — calls the A2A Multi-Agent Research FastAPI backend.

The exporter is fixed at service startup via EXPORTER_A2A in .env.
This UI does not offer a dropdown to change it — use the service status
table to verify all three processes are using the same exporter.
"""

import os
from datetime import datetime

import gradio as gr
import httpx

BACKEND_URL    = os.getenv("BACKEND_A2A_URL", "http://localhost:8002")
RESEARCHER_URL = os.getenv("RESEARCHER_URL",  "http://localhost:8011")
EVALUATOR_URL  = os.getenv("EVALUATOR_URL",   "http://localhost:8012")

EXAMPLES = [
    ["What are the main observability tools for LLM agents in 2025?"],
    ["How does LangSmith compare to Langfuse for LLM tracing?"],
    ["What is OpenTelemetry and how is it used in AI systems?"],
    ["What are best practices for monitoring multi-agent AI pipelines?"],
    ["How does Arize Phoenix support LLM evaluation?"],
    ["What is the difference between tracing and logging in AI observability?"],
]

_SERVICES = [
    ("orchestrator", BACKEND_URL),
    ("researcher",   RESEARCHER_URL),
    ("evaluator",    EVALUATOR_URL),
]


def _new_session_id() -> str:
    return f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _fetch_service_status() -> str:
    rows = ["| Service | Port | Exporter | |", "|---|---|---|---|"]
    for name, url in _SERVICES:
        port = url.split(":")[-1]
        try:
            r = httpx.get(f"{url}/health", timeout=3)
            data = r.json()
            exporter = data.get("exporter", "?")
            icon = "✓" if exporter not in ("none", "?") else "○"
        except Exception:
            exporter, icon = "unreachable", "✗"
        rows.append(f"| `{name}` | `:{port}` | `{exporter}` | {icon} |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# State and event handlers
# ---------------------------------------------------------------------------

_state: dict = {"session_id": ""}


def _make_default_session() -> str:
    """Called by Gradio when rendering the session box.
    Generates a fresh session ID and stores it in _state so that the first
    chat message uses the same ID that is displayed in the textbox.
    Without this, _state["session_id"] starts as "" and each message gets a
    different throwaway ID, preventing Phoenix from grouping traces by session.
    """
    sid = _new_session_id()
    _state["session_id"] = sid
    return sid


def _reset_backend_session(sid: str) -> None:
    if sid:
        try:
            httpx.delete(f"{BACKEND_URL}/session/{sid}", timeout=5)
        except Exception:
            pass


def set_session(session_id: str) -> str:
    _state["session_id"] = session_id
    return session_id


def new_session():
    _reset_backend_session(_state["session_id"])
    sid = _new_session_id()
    _state["session_id"] = sid
    return sid, []


def chat(message: str, session_id: str) -> str:
    response = httpx.post(
        f"{BACKEND_URL}/chat",
        json={"query": message, "session_id": session_id},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()

    hitl_warning = (
        "\n\n⚠️ **HITL escalation required** — confidence too low after retries."
        if data["hitl_required"] else ""
    )
    scores = f"\n\n---\n**Faithfulness:** `{data['faithfulness']:.2f}`"
    return data["final_answer"] + scores + hitl_warning


def _chat(message: str, _history: list) -> str:
    session_id = _state["session_id"] or _new_session_id()
    return chat(message, session_id)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

with gr.Blocks(title="Multi-Agent Research (A2A v2)") as demo:
    gr.Markdown(
        "## Multi-Agent Research (A2A v2)\n"
        "Research queries answered by Researcher → Evaluator → Orchestrator over A2A JSON-RPC.\n\n"
        "The active exporter is configured via `EXPORTER_A2A` in `.env` and fixed at startup."
    )

    with gr.Row():
        with gr.Column(scale=4):
            service_status = gr.Markdown(_fetch_service_status, label="Service status")
        with gr.Column(scale=1, min_width=160):
            refresh_btn = gr.Button("↻ Refresh status", size="sm")

    with gr.Row():
        session_box = gr.Textbox(
            label="Session ID", value=_make_default_session,
            interactive=True, scale=4,
        )
        new_session_btn = gr.Button("New Session", scale=1)

    session_box.change(fn=set_session, inputs=session_box, outputs=session_box)

    chat_interface = gr.ChatInterface(fn=_chat)

    refresh_btn.click(fn=_fetch_service_status, outputs=service_status)
    new_session_btn.click(fn=new_session, outputs=[session_box, chat_interface.chatbot])

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
    demo.launch()
