from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

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
    tool_calls: tuple[ToolCall, ...] = ()
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


@dataclass(kw_only=True)
class AgentState:
    """Holds the current state and memory of the agent."""

    messages: list[Message] = field(default_factory=list)
    step_count: int = 0
