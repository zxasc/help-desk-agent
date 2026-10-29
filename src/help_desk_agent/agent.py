import asyncio
import inspect
import json
import logging
from collections.abc import Callable
from datetime import datetime

from help_desk_agent.core import (
    CURRENT_TIME,
    AgentResult,
    AgentState,
    ChatModel,
    Message,
    Tool,
    ToolCall,
    ToolRun,
)
from help_desk_agent.exceptions import ToolException

logger = logging.getLogger(__name__)

MAX_STEPS_REACHED = "Agent stopped: Reached maximum steps without a final answer."


class Agent:
    def __init__(
        self,
        llm_client: ChatModel,
        tools: dict[str, Tool],
        max_steps: int = 5,
        now: datetime = CURRENT_TIME,
        on_tool_run: Callable[[ToolRun], None] | None = None,
    ):
        self.llm = llm_client
        self.tools = tools
        self.max_steps = max_steps
        self.now = now
        self.on_tool_run = on_tool_run

    def _build_system_prompt(self) -> str:
        return f"""You are the help desk assistant of CityWheels, a small bike rental shop.
You answer customer questions about opening hours, prices, bookings, cancellations and refunds.
The current date and time is {self.now:%Y-%m-%d %H:%M} (Europe/Warsaw, UTC{self.now:%z}). Use it for every "now", "today" or "tomorrow".

RULES:
1. Answer only from tool results. Never use your general knowledge about bike rentals or other shops.
2. For questions about rules, prices, opening hours or other shop information, call search_policies first.
3. For questions about a specific booking, call get_booking with the booking number (for example CW-1001).
   If the booking is not found, tell the customer and ask them to check the number. Never guess booking details.
4. Never calculate refund amounts yourself. Always call calculate_refund and repeat the amounts it returns exactly.
5. Never make up booking details, amounts, dates or rules that are not in a tool result.
6. If the tool results do not answer the question, or the question is not about CityWheels,
   say that you cannot help with it and tell the customer to contact the CityWheels staff.
   Use search_policies to find the staff contact details.
7. Answer in the customer's language. Be short, friendly and concrete.
"""

    async def _call_tool(self, tool: Tool, args: dict) -> str:
        if inspect.iscoroutinefunction(tool.func):
            result = await tool.func(**args)
        else:
            result = await asyncio.to_thread(tool.func, **args)
        return result if isinstance(result, str) else json.dumps(result)

    async def _run_tool_call(self, call: ToolCall) -> str:
        tool = self.tools.get(call.name)
        if tool is None:
            return f"Error: Tool '{call.name}' not found."
        try:
            args = json.loads(call.arguments)
        except json.JSONDecodeError as e:
            return f"Error: Arguments for '{call.name}' are not valid JSON: {e}"
        if not isinstance(args, dict):
            return f"Error: Arguments for '{call.name}' must be a JSON object."
        try:
            return await self._call_tool(tool, args)
        except ToolException as e:
            return f"Tool execution failed: {e!s}"
        except TypeError as e:
            # Wrong or missing argument names from the model
            return f"Error: Invalid arguments for '{call.name}': {e}"

    async def run(self, query: str) -> AgentResult:
        state = AgentState()
        # Initialize context with System Prompt and User Query
        state.messages.append(
            Message(role="system", content=self._build_system_prompt())
        )
        state.messages.append(Message(role="user", content=query))

        for _ in range(self.max_steps):
            state.step_count += 1

            reply = await self.llm(state.messages, tools=list(self.tools.values()))
            logger.debug("Step %d LLM reply: %s", state.step_count, reply)
            state.messages.append(reply)

            if not reply.tool_calls:
                if not reply.content:
                    logger.warning(
                        "Step %d: LLM reply has neither text nor tool calls",
                        state.step_count,
                    )
                return AgentResult(answer=reply.content, tool_runs=state.tool_runs)

            for call in reply.tool_calls:
                tool_run = ToolRun(call=call, result=await self._run_tool_call(call))
                logger.info("Step %d: ran tool %s", state.step_count, call.name)
                state.tool_runs.append(tool_run)
                if self.on_tool_run:
                    self.on_tool_run(tool_run)
                state.messages.append(
                    Message(role="tool", content=tool_run.result, tool_call_id=call.id)
                )

        return AgentResult(answer=MAX_STEPS_REACHED, tool_runs=state.tool_runs)
