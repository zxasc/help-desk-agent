import asyncio
import inspect
import json
import logging
from datetime import datetime

from help_desk_agent.core import CURRENT_TIME, AgentState, Message, Tool, ToolCall
from help_desk_agent.exceptions import ToolException
from help_desk_agent.llm_client import LLMClient

logger = logging.getLogger(__name__)


class Agent:
    def __init__(
        self,
        llm_client: LLMClient,
        tools: dict[str, Tool],
        max_steps: int = 5,
        now: datetime = CURRENT_TIME,
    ):
        self.llm = llm_client
        self.tools = tools
        self.max_steps = max_steps
        self.now = now

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
        return str(result)

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

    async def run(self, query: str) -> str | None:
        state = AgentState()
        # Initialize context with System Prompt and User Query
        state.messages.append(
            Message(role="system", content=self._build_system_prompt())
        )
        state.messages.append(Message(role="user", content=query))

        print(f"USER: {query}\n" + "-" * 40)

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
                print(f"✅ FINAL ANSWER: {reply.content}")
                return reply.content

            if reply.content:
                print(f"🤔 THOUGHT: {reply.content}")

            for call in reply.tool_calls:
                print(f"🛠️ ACTION: {call.name} | INPUT: {call.arguments}")
                observation = await self._run_tool_call(call)
                print(f"👀 OBSERVATION: {observation}\n" + "-" * 40)
                state.messages.append(
                    Message(role="tool", content=observation, tool_call_id=call.id)
                )

        return "Agent stopped: Reached maximum steps without a final answer."
