import os
from dotenv import load_dotenv
import langwatch
from langchain_core.runnables import RunnableConfig
from langchain.tools import tool
from langchain.chat_models import init_chat_model

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
langwatch.setup()

# Step 1: Define tools and model
model = init_chat_model(
    "gpt-4o",
    temperature=0
)


# Define tools
@tool
def multiply(a: int, b: int) -> int:
    """Multiply `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a * b


@tool
def add(a: int, b: int) -> int:
    """Adds `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a + b


@tool
def divide(a: int, b: int) -> float:
    """Divide `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a / b


# Augment the LLM with tools
tools = [add, multiply, divide]
tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = model.bind_tools(tools)

from langgraph.graph import add_messages
from langchain.messages import (
    SystemMessage,
    HumanMessage,
    ToolCall,
)
from langchain_core.messages import BaseMessage
from langgraph.func import entrypoint, task


# Step 2: Define model node

@task
def call_llm(messages: list[BaseMessage]):
    """LLM decides whether to call a tool or not"""
    # Get the callback handler to capture this specific LLM call
    return model_with_tools.invoke(
        [
            SystemMessage(
                content="You are a helpful assistant tasked with performing arithmetic."
            )
        ] + messages,
        config=RunnableConfig(
            callbacks=[langwatch.get_current_trace().get_langchain_callback()]
        ),
    )


# Step 3: Define tool node
@task
def call_tool(tool_call: ToolCall):
    """Performs the tool call"""
    tool = tools_by_name[tool_call["name"]]
    return tool.invoke(tool_call)


# Step 4: Define agent
@entrypoint()
@langwatch.trace(name="Arithmetic Agent")
def agent(messages: list[BaseMessage]):
    model_response = call_llm(messages).result()

    while True:
        if not model_response.tool_calls:
            break

        # Execute tools
        tool_result_futures = [
            call_tool(tool_call) for tool_call in model_response.tool_calls
        ]
        tool_results = [fut.result() for fut in tool_result_futures]
        messages = add_messages(messages, [model_response, *tool_results])
        model_response = call_llm(messages).result()

    messages = add_messages(messages, model_response)
    return messages


# Invoke
messages = [HumanMessage(content="Add 3 and 4.")]
for chunk in agent.stream(messages, stream_mode="updates"):
    print(chunk)
    print("\n")

