from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

# Fixed "now" from the assignment README, so answers are the same on every run
CURRENT_TIME = datetime(2026, 6, 10, 9, 0, tzinfo=timezone(timedelta(hours=2)))


@dataclass(frozen=True, kw_only=True)
class ToolCall:
    """Represents the LLM's request to run one tool."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True, kw_only=True)
class Message:
    """Represents a chat message in the conversation history."""

    role: str
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # set on role="tool" messages


@dataclass(frozen=True, kw_only=True)
class Tool:
    """Represents an executable function the agent can call."""

    name: str
    description: str
    func: Callable
    parameters: dict[str, Any]  # JSON Schema of the function arguments

    def schema(self) -> dict[str, Any]:
        """Tool definition in the OpenAI-compatible `tools` format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True, kw_only=True)
class ToolRun:
    """One tool call the agent made, and the result it sent back to the model."""

    call: ToolCall
    result: str


@dataclass(frozen=True, kw_only=True)
class AgentResult:
    """The agent's answer and every tool it ran to get there."""

    answer: str | None
    tool_runs: list[ToolRun] = field(default_factory=list)


class ChatModel(Protocol):
    """Anything that returns the model's next message, e.g. LLMClient or a test fake."""

    async def __call__(
        self, messages: list[Message], tools: list[Tool] | None = None
    ) -> Message: ...


@dataclass(kw_only=True)
class AgentState:
    """Holds the current state and memory of the agent."""

    messages: list[Message] = field(default_factory=list)
    tool_runs: list[ToolRun] = field(default_factory=list)
    step_count: int = 0
