import httpx

from src.ui import build_demo

BACKEND_URL = "http://localhost:8000"

EXAMPLES = [
    ["What is 6 multiplied by 7?"],
    ["What is 123 plus 456?"],
    ["Divide 100 by 4, then add 13."],
    ["Multiply 8 by 9, then divide the result by 6."],
    ["What is 15 divided by 3?"],
    ["Add 27 and 73, then multiply by 2."],
]


def chat(message: str, _history: list, exporter: str, session_id: str) -> str:
    response = httpx.post(
        f"{BACKEND_URL}/chat",
        json={"message": message, "exporter": exporter, "session_id": session_id},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["response"]


demo = build_demo(
    backend_url=BACKEND_URL,
    title="Simple Agent",
    description="Arithmetic agent with pluggable observability tracing.",
    examples=EXAMPLES,
    chat_fn=chat,
)

if __name__ == "__main__":
    demo.launch()
