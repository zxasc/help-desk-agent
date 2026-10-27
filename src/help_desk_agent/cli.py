import asyncio
import os

import click
import httpx2
from dotenv import find_dotenv, load_dotenv

from help_desk_agent.agent import Agent
from help_desk_agent.llm_client import LLMClient

REQUIRED_ENV_VARS = ("LLM_API_KEY", "LLM_API_URL")


@click.group()
def cli() -> None:
    """CityWheel help desk agent."""
    load_dotenv()


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
    agent = Agent(LLMClient(), tools={}, max_steps=max_steps)
    asyncio.run(agent.run(query))


if __name__ == "__main__":
    cli()
