"""Shared Gradio UI factory for all agent frontends.

build_demo() wires the common layout — exporter selector, session management,
chat interface, and example table — and delegates only the chat response
handling to the caller-supplied chat_fn.

chat_fn signature: (message: str, history: list, exporter: str, session_id: str) -> str
"""

from datetime import datetime
from typing import Callable

import gradio as gr
import httpx

EXPORTERS = ["langfuse", "phoenix", "opik", "otel-stdout", "none"]


def _new_session_id() -> str:
    return f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def build_demo(
    backend_url: str,
    title: str,
    description: str,
    examples: list[list[str]],
    chat_fn: Callable[[str, list, str, str], str],
) -> gr.Blocks:
    """Return a configured gr.Blocks demo ready for .launch().

    Parameters
    ----------
    backend_url:
        Base URL of the FastAPI backend (e.g. "http://localhost:8000").
    title:
        Browser tab title.
    description:
        Markdown rendered at the top of the page.
    examples:
        List of [[question]] rows shown in the example table.
    chat_fn:
        Called as chat_fn(message, history, exporter, session_id) → reply string.
"""
    state: dict = {"exporter": "none", "session_id": ""}

    def _reset_backend_session(old_sid: str) -> None:
        if old_sid:
            try:
                httpx.delete(f"{backend_url}/session/{old_sid}", timeout=5)
            except Exception:
                pass

    def activate_exporter(exporter: str) -> tuple:
        state["exporter"] = exporter
        # New exporter → new session so traces aren't mixed across tools.
        _reset_backend_session(state["session_id"])
        sid = _new_session_id()
        state["session_id"] = sid
        try:
            r = httpx.post(f"{backend_url}/exporter/{exporter}", timeout=10)
            r.raise_for_status()
            data = r.json()
            status = "active" if data["active"] else "failed to initialise"
            msg = f"Exporter: {data['exporter']} — {status} ({data['collector_url']})"
        except Exception as e:
            msg = f"Could not activate exporter: {e}"
        return msg, sid, []

    def set_session(session_id: str) -> str:
        state["session_id"] = session_id
        return session_id

    def new_session() -> tuple:
        _reset_backend_session(state["session_id"])
        sid = _new_session_id()
        state["session_id"] = sid
        return sid, []

    def _chat(message: str, history: list) -> str:
        exporter   = state["exporter"]
        session_id = state["session_id"] or _new_session_id()
        return chat_fn(message, history, exporter, session_id)

    with gr.Blocks(title=title) as demo:
        gr.Markdown(f"## {title}\n{description}")

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

        with gr.Row():
            session_box = gr.Textbox(
                label="Session ID",
                value=_new_session_id,
                interactive=True,
                scale=4,
            )
            new_session_btn = gr.Button("New Session", scale=1)

        session_box.change(fn=set_session, inputs=session_box, outputs=session_box)

        chat_interface = gr.ChatInterface(fn=_chat)

        # Wire exporter change and new-session button after chat_interface is created
        # so we can clear chat_interface.chatbot as part of the same event.
        exporter_dd.change(
            fn=activate_exporter,
            inputs=exporter_dd,
            outputs=[exporter_status, session_box, chat_interface.chatbot],
        )
        new_session_btn.click(
            fn=new_session,
            outputs=[session_box, chat_interface.chatbot],
        )

        gr.Markdown("### Example questions")
        example_table = gr.Dataset(
            components=[gr.Textbox(visible=False)],
            samples=examples,
            headers=["Click a question to load it into the chat"],
            type="index",
        )
        example_table.click(
            fn=lambda idx: examples[idx][0],
            inputs=example_table,
            outputs=chat_interface.textbox,
        )

    return demo
