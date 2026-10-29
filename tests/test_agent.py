import asyncio
import json
from dataclasses import dataclass

import pytest

from help_desk_agent.agent import Agent
from help_desk_agent.core import Message, Tool, ToolCall
from help_desk_agent.exceptions import ToolException

QUESTION = "Is booking CW-1001 confirmed?"
FINAL_ANSWER = "Yes, booking CW-1001 is confirmed."
BOOKING_ID = "CW-1001"
TOOL_CALL_ID = "call-1"
BOOKING_ARGUMENTS = json.dumps({"booking_id": BOOKING_ID})
FAILURE_REASON = "booking file is broken"
MAX_STEPS = 3
MAX_STEPS_REACHED = "Agent stopped: Reached maximum steps without a final answer."

FIRST_CALL = 0
LAST_CALL = -1
LAST_MESSAGE = -1
# The assistant's tool call and the tool result that answers it
TOOL_EXCHANGE = slice(-2, None)


def lookup(booking_id: str) -> dict[str, str]:
    return {"booking_id": booking_id, "status": "confirmed"}


async def async_lookup(booking_id: str) -> dict[str, str]:
    return lookup(booking_id)


def text_lookup(booking_id: str) -> str:
    return f"{booking_id} is confirmed"


def failing_lookup(booking_id: str) -> str:
    raise ToolException(FAILURE_REASON)


def _fake_tool(func) -> Tool:
    return Tool(
        name=func.__name__,
        description=f"Fake {func.__name__} tool.",
        func=func,
        parameters={
            "type": "object",
            "properties": {"booking_id": {"type": "string"}},
            "required": ["booking_id"],
        },
    )


TOOLS = {
    tool.name: tool
    for tool in map(_fake_tool, (lookup, async_lookup, text_lookup, failing_lookup))
}


@dataclass(frozen=True)
class FakeCall:
    messages: list[Message]
    tool_names: list[str]


class FakeChatModel:
    """Replies with scripted messages and records what the agent sent each time."""

    def __init__(self, replies: list[Message]):
        self._replies = list(replies)
        self.calls: list[FakeCall] = []

    async def __call__(
        self, messages: list[Message], tools: list[Tool] | None = None
    ) -> Message:
        # Copy: the agent keeps appending to the same list after this call
        self.calls.append(
            FakeCall(messages=list(messages), tool_names=[t.name for t in tools or []])
        )
        if not self._replies:
            raise AssertionError("The agent asked the fake model for too many replies")
        return self._replies.pop(0)


def tool_call_reply(name: str, arguments: str) -> Message:
    return Message(
        role="assistant",
        tool_calls=[ToolCall(id=TOOL_CALL_ID, name=name, arguments=arguments)],
    )


FINAL_REPLY = Message(role="assistant", content=FINAL_ANSWER)


def run_agent(model: FakeChatModel) -> str | None:
    return asyncio.run(Agent(model, TOOLS, max_steps=MAX_STEPS).run(QUESTION))


@pytest.mark.parametrize(
    "replies",
    [
        pytest.param([FINAL_REPLY], id="text reply is the final answer"),
        pytest.param(
            [tool_call_reply("lookup", BOOKING_ARGUMENTS), FINAL_REPLY],
            id="text reply after a tool call is the final answer",
        ),
    ],
)
def test_agent_returns_final_answer(replies):
    assert run_agent(FakeChatModel(replies)) == FINAL_ANSWER


def test_agent_sends_system_prompt_question_and_tools_to_model():
    model = FakeChatModel([FINAL_REPLY])
    run_agent(model)
    first_call = model.calls[FIRST_CALL]
    expected = {
        "roles": ["system", "user"],
        "question": QUESTION,
        "tool_names": list(TOOLS),
    }

    assert {
        "roles": [m.role for m in first_call.messages],
        "question": first_call.messages[LAST_MESSAGE].content,
        "tool_names": first_call.tool_names,
    } == expected


@dataclass(frozen=True, kw_only=True)
class ToolResultCase:
    id: str
    tool_name: str
    arguments: str = BOOKING_ARGUMENTS
    expected_result: str


TOOL_RESULT_CASES = [
    ToolResultCase(
        id="sync tool result is sent as JSON",
        tool_name="lookup",
        expected_result=json.dumps(lookup(BOOKING_ID)),
    ),
    ToolResultCase(
        id="async tool result is sent as JSON",
        tool_name="async_lookup",
        expected_result=json.dumps(lookup(BOOKING_ID)),
    ),
    ToolResultCase(
        id="text tool result is sent unchanged",
        tool_name="text_lookup",
        expected_result=text_lookup(BOOKING_ID),
    ),
    ToolResultCase(
        id="unknown tool is reported to the model",
        tool_name="missing_tool",
        expected_result="Error: Tool 'missing_tool' not found.",
    ),
    ToolResultCase(
        id="invalid JSON arguments are reported to the model",
        tool_name="lookup",
        arguments="{not json",
        expected_result="Error: Arguments for 'lookup' are not valid JSON: "
        "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)",
    ),
    ToolResultCase(
        id="non object arguments are reported to the model",
        tool_name="lookup",
        arguments=json.dumps([BOOKING_ID]),
        expected_result="Error: Arguments for 'lookup' must be a JSON object.",
    ),
    ToolResultCase(
        id="wrong argument names are reported to the model",
        tool_name="lookup",
        arguments=json.dumps({"id": BOOKING_ID}),
        expected_result="Error: Invalid arguments for 'lookup': "
        "lookup() got an unexpected keyword argument 'id'",
    ),
    ToolResultCase(
        id="tool failure is reported to the model",
        tool_name="failing_lookup",
        expected_result=f"Tool execution failed: {FAILURE_REASON}",
    ),
]


@pytest.mark.parametrize("case", TOOL_RESULT_CASES, ids=lambda case: case.id)
def test_agent_sends_tool_result_back_to_model(case: ToolResultCase):
    call_reply = tool_call_reply(case.tool_name, case.arguments)
    model = FakeChatModel([call_reply, FINAL_REPLY])
    run_agent(model)
    expected = [
        call_reply,
        Message(role="tool", content=case.expected_result, tool_call_id=TOOL_CALL_ID),
    ]

    assert model.calls[LAST_CALL].messages[TOOL_EXCHANGE] == expected


def test_agent_stops_after_max_steps_without_final_answer():
    model = FakeChatModel([tool_call_reply("lookup", BOOKING_ARGUMENTS)] * MAX_STEPS)
    result = run_agent(model)

    assert (result, len(model.calls)) == (MAX_STEPS_REACHED, MAX_STEPS)
