import asyncio
import logging
import os

import click
import httpx2
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.text import Text

from help_desk_agent.agent import Agent
from help_desk_agent.core import ToolRun
from help_desk_agent.exceptions import LLMException
from help_desk_agent.llm_client import LLMClient
from help_desk_agent.tools import TOOLS

REQUIRED_ENV_VARS = ("LLM_API_KEY", "LLM_API_URL")
LOG_LEVELS = ("debug", "info", "warning", "error")

# ask -v shows which tools ran, -vv also shows their arguments and results
VERBOSITY_LEVEL_SHOW_TOOL_NAMES = 1
VERBOSITY_LEVEL_SHOW_TOOL_DETAILS = 2

QUERY_PROMPT = ">"
ANSWER_LABEL = "CityWheels Support:"

logger = logging.getLogger(__name__)

# The answer goes to stdout; the spinner, tool trace and logs go to stderr
console = Console()
err_console = Console(stderr=True)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(name)s: %(message)s",
        handlers=[RichHandler(console=err_console, show_path=False)],
    )
    # Connection-level internals are very noisy even at debug level
    for name in ("httpcore2", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _show_tool_run(tool_run: ToolRun, verbosity: int) -> None:
    if verbosity >= VERBOSITY_LEVEL_SHOW_TOOL_DETAILS:
        call = tool_run.call
        err_console.print(Text(f"→ {call.name} {call.arguments}", style="dim"))
        err_console.print(Text(f"  {tool_run.result}", style="dim"))
    elif verbosity >= VERBOSITY_LEVEL_SHOW_TOOL_NAMES:
        err_console.print(Text(f"→ used {tool_run.call.name}", style="dim"))


@click.group()
@click.option(
    "--log-level",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    default="warning",
    show_default=True,
    help="Log messages to stderr from this level up.",
)
def cli(log_level: str) -> None:
    """CityWheel help desk agent."""
    _configure_logging(log_level)
    env_path = find_dotenv(usecwd=True)
    logger.debug("Loading env from %s", env_path or "process environment only")
    load_dotenv(env_path)


@cli.command("check-health")
@click.option(
    "--timeout", default=10.0, show_default=True, help="Ping timeout in seconds."
)
def check_health(timeout: float) -> None:
    """Check the .env configuration and ping the LLM provider."""
    env_path = find_dotenv(usecwd=True)
    if env_path:
        click.echo(f"✅ .env found: {env_path}")
    else:
        click.echo("⚠️  No .env file found, using process environment only")

    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise click.ClickException(f"Missing env vars: {', '.join(missing)}")
    click.echo(f"✅ Env vars set: {', '.join(REQUIRED_ENV_VARS)}")

    api_url = os.environ["LLM_API_URL"].rstrip("/")
    try:
        response = httpx2.get(
            f"{api_url}/models",
            headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
            timeout=timeout,
        )
    except httpx2.HTTPError as exc:
        raise click.ClickException(f"Cannot reach {api_url}: {exc}") from exc

    if response.is_error:
        raise click.ClickException(
            f"{api_url}/models returned HTTP {response.status_code}: {response.text[:200]}"
        )
    click.echo(f"✅ Provider reachable: {api_url} (HTTP {response.status_code})")


@cli.command()
@click.argument("query")
@click.option(
    "--max-steps", default=5, show_default=True, help="Max agent reasoning steps."
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Show tool calls: -v tool names, -vv also arguments and results.",
)
def ask(query: str, max_steps: int, verbose: int) -> None:
    """Ask the agent a QUERY."""
    agent = Agent(
        LLMClient(),
        tools=TOOLS,
        max_steps=max_steps,
        on_tool_run=lambda tool_run: _show_tool_run(tool_run, verbose),
    )
    console.print(Text(f"{QUERY_PROMPT} {query}"))
    try:
        with err_console.status("Thinking…"):
            result = asyncio.run(agent.run(query))
    except LLMException as exc:
        raise click.ClickException(f"Agent couldn't answer {query!r}: {exc}") from exc

    if not result.answer:
        raise click.ClickException("The agent returned an empty answer.")
    console.print()
    console.print(Markdown(f"**{ANSWER_LABEL}** {result.answer}"))


if __name__ == "__main__":
    cli()
