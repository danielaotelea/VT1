from lang_graph_simple import build_agent, main, add
from langchain.schema import HumanMessage


class FakeModel:
    def __init__(self):
        self.calls = []

    def invoke(self, messages, config=None):
        # emulate a model that asks for a tool call when asked to add numbers
        # if the user message content starts with 'Add', create a fake tool_call
        last = messages[-1]
        text = getattr(last, "content", "")
        if text.startswith("Add"):
            # construct a minimal object with tool_calls attribute
            class TC:
                def __init__(self):
                    self.tool_calls = [{"name": "add", "args": [13, 37], "id": "1"}]

            return TC()
        # otherwise just return a message-like object
        return HumanMessage(content="No action needed")


def test_agent_with_fake_model():
    fake = FakeModel()
    agent = build_agent(model=fake)
    # run the agent via the public main() helper
    out = main("Add 13 and 37.", agent=agent)
    assert "[tool:add" in out or "50" in out

