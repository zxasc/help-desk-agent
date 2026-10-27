import asyncio
import inspect
import json

from help_desk_agent.core import Action, AgentState, Message, Tool
from help_desk_agent.exceptions import ToolException
from help_desk_agent.llm_client import LLMClient


class Agent:
    def __init__(
        self, llm_client: LLMClient, tools: dict[str, Tool], max_steps: int = 5
    ):
        self.llm = llm_client
        self.tools = tools
        self.max_steps = max_steps

    def _build_system_prompt(self) -> str:
        tool_descriptions = "\n".join(
            f"- {name}: {t.description} (Args: {t.parameters})"
            for name, t in self.tools.items()
        )

        return f"""You are an autonomous AI assistant. You solve problems by reasoning and using tools.

AVAILABLE TOOLS:
{tool_descriptions}

FORMAT INSTRUCTIONS:
You must strictly follow this format for EVERY turn.

Thought: Explain your reasoning for the next step.
Action: The name of the tool to use (or "FINAL_ANSWER").
Action Input: A valid JSON object representing the tool arguments (or your final response to the user).

If you are ready to answer the user, use Action: FINAL_ANSWER.
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
