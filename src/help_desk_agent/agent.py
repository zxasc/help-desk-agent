import asyncio
import inspect
import json
from datetime import datetime

from help_desk_agent.core import CURRENT_TIME, Action, AgentState, Message, Tool
from help_desk_agent.exceptions import ToolException
from help_desk_agent.llm_client import LLMClient


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
        tool_descriptions = "\n".join(
            f"- {name}: {t.description} (Args: {t.parameters})"
            for name, t in self.tools.items()
        )

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

AVAILABLE TOOLS:
{tool_descriptions}

FORMAT INSTRUCTIONS:
You must strictly follow this format for EVERY turn.

Thought: Explain your reasoning for the next step.
Action: The name of the tool to use (or "FINAL_ANSWER").
Action Input: For a tool, a valid JSON object with the tool arguments. For FINAL_ANSWER, your answer to the customer as plain text, not JSON.

Write each of the three lines on a single line. Call one tool per turn and wait for its Observation.
When you are ready to answer the customer, use Action: FINAL_ANSWER.
"""

    def _parse_response(self, text: str) -> Action:
        thought, action, action_input = "", "", ""
        for line in text.split("\n"):
            if line.startswith("Thought:"):
                thought = line.replace("Thought:", "").strip()
            elif line.startswith("Action:"):
                action = line.replace("Action:", "").strip()
            elif line.startswith("Action Input:"):
                action_input = line.replace("Action Input:", "").strip()

        return Action(thought=thought, action_name=action, action_input=action_input)

    async def _call_tool(self, tool: Tool, args: dict) -> str:
        if inspect.iscoroutinefunction(tool.func):
            result = await tool.func(**args)
        else:
            result = await asyncio.to_thread(tool.func, **args)
        return str(result)

    async def run(self, query: str) -> str | None:
        state = AgentState()
        # Initialize context with System Prompt and User Query
        state.messages.append(
            Message(role="system", content=self._build_system_prompt())
        )
        state.messages.append(Message(role="user", content=query))

        print(f"USER: {query}\n" + "-" * 40)

        for step in range(self.max_steps):
            state.step_count += 1

            # 1. Ask the LLM what to do next
            llm_response = await self.llm(state.messages)
            action = self._parse_response(llm_response)

            print(f"🤔 THOUGHT: {action.thought}")

            # 2. Check for completion
            if action.action_name == "FINAL_ANSWER":
                print(f"✅ FINAL ANSWER: {action.action_input}")
                return action.action_input

            # 3. Execute Tool
            print(f"🛠️ ACTION: {action.action_name} | INPUT: {action.action_input}")
            if action.action_name in self.tools:
                try:
                    args = json.loads(action.action_input or "{}")
                    tool = self.tools[action.action_name]
                    observation = await self._call_tool(tool, args)
                except ToolException as e:
                    observation = f"Tool execution failed: {e!s}"
            else:
                observation = f"Error: Tool '{action.action_name}' not found."

            print(f"👀 OBSERVATION: {observation}\n" + "-" * 40)

            state.messages.append(Message(role="assistant", content=llm_response))
            state.messages.append(
                Message(role="user", content=f"Observation: {observation}")
            )

        return "Agent stopped: Reached maximum steps without a final answer."
