import asyncio
import logging
import os

import click
import httpx2
from dotenv import find_dotenv, load_dotenv

from help_desk_agent.agent import Agent
from help_desk_agent.exceptions import LLMException
from help_desk_agent.llm_client import LLMClient
from help_desk_agent.tools import TOOLS

REQUIRED_ENV_VARS = ("LLM_API_KEY", "LLM_API_URL")


logger = logging.getLogger(__name__)


def _configure_logging(verbosity: int) -> None:
    level = {0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if verbosity < 3:
        # Connection-level internals are very noisy, only show them at -vvv
        for name in ("httpcore2", "asyncio"):
            logging.getLogger(name).setLevel(logging.WARNING)


@click.group()
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Log to stderr: -v info, -vv debug, -vvv include HTTP internals.",
)
def cli(verbose: int) -> None:
    """CityWheel help desk agent."""
    _configure_logging(verbose)
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
def ask(query: str, max_steps: int) -> None:
    """Ask the agent a QUERY."""
    agent = Agent(LLMClient(), tools=TOOLS, max_steps=max_steps)
    try:
        asyncio.run(agent.run(query))
    except LLMException as exc:
        raise click.ClickException(f"Agent couldn't answer {query!r}: {exc}") from exc


if __name__ == "__main__":
    cli()
