from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# Fixed "now" from the assignment README, so answers are the same on every run
CURRENT_TIME = datetime(2026, 6, 10, 9, 0, tzinfo=timezone(timedelta(hours=2)))


@dataclass(frozen=True, kw_only=True)
class Message:
    """Represents a chat message in the conversation history."""

    role: str
    content: str


@dataclass(frozen=True, kw_only=True)
class Tool:
    """Represents an executable function the agent can call."""

    name: str
    description: str
    func: Callable
    parameters: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class Action:
    """Represents the LLM's decision for the current step."""

    thought: str
    action_name: str | None = None
    action_input: str | None = None


@dataclass(kw_only=True)
class AgentState:
    """Holds the current state and memory of the agent."""

    messages: list[Message] = field(default_factory=list)
    step_count: int = 0
