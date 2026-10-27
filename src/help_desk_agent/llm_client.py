import logging
import os
import time
from typing import Any

import httpx2
from dotenv import load_dotenv
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from help_desk_agent.core import Message, Tool, ToolCall
from help_desk_agent.exceptions import LLMException

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("LLM_MODEL", "gemini-3.8-flash")


RETRY_STATUS = {429, 500, 502, 503, 504}


def _log_retry(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, httpx2.HTTPStatusError):
        reason = f"HTTP {exc.response.status_code}"
    else:
        reason = repr(exc)
    logger.warning(
        "Attempt %d failed (%s), retrying in %.1fs",
        retry_state.attempt_number,
        reason,
        retry_state.upcoming_sleep,
    )


class LLMClient:
    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL,
        timeout: float = 30.0,
        temperature: float = 0.2,
        max_tokens: int = 10000,
        max_retries: int = 5,
    ):
        self.model = model_name
        self.temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._api_key = os.getenv("LLM_API_KEY")
        self._api_url = os.getenv("LLM_API_URL")
        self._http = httpx2.AsyncClient(
            base_url=str(self._api_url).rstrip("/") + "/",
            headers={"Authorization": f"Bearer {self._api_key}"}
            if self._api_key
            else {},
            timeout=timeout,
            transport=httpx2.AsyncHTTPTransport(retries=3),
        )
        logger.debug(
            "LLMClient ready: model=%s url=%s api_key=%s",
            self.model,
            self._http.base_url,
            "set" if self._api_key else "MISSING",
        )

    async def __call__(
        self, messages: list[Message], tools: list[Tool] | None = None
    ) -> Message:
        payload = self._create_payload(messages, tools or [])
        logger.info("Calling %s with %d messages", self.model, len(payload["messages"]))
        logger.debug("Request payload: %s", payload)
        started = time.perf_counter()

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries),
                retry=retry_if_exception_type(httpx2.HTTPError),
                wait=wait_random_exponential(multiplier=1, max=30),
                before_sleep=_log_retry,
                reraise=True,
            ):
                with attempt:
                    response = await self._http.post("chat/completions", json=payload)
                    if response.status_code in RETRY_STATUS:
                        response.raise_for_status()
        except httpx2.HTTPStatusError as exc:
            raise LLMException(
                f"Provider returned HTTP {exc.response.status_code}: {exc.response.text[:500]}"
            ) from exc
        except httpx2.HTTPError as exc:
            raise LLMException(f"Cannot reach the model provider: {exc}") from exc

        logger.info(
            "Provider answered HTTP %d in %.2fs",
            response.status_code,
            time.perf_counter() - started,
        )
        logger.debug("Response body: %s", response.text)

        if response.is_error:
            raise LLMException(
                f"Provider returned HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") == "length":
                logger.warning(
                    "Reply cut off at max_tokens=%d, reasoning models may leave no text",
                    self._max_tokens,
                )
            return self._parse_message(choice["message"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMException(
                f"Unexpected response from provider: {response.text[:500]}"
            ) from exc

    def _create_payload(
        self, messages: list[Message], tools: list[Tool]
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._serialize_message(m) for m in messages],
            "max_tokens": self._max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = [t.schema() for t in tools]
        return payload

    @staticmethod
    def _serialize_message(message: Message) -> dict[str, Any]:
        data: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            data["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id:
            data["tool_call_id"] = message.tool_call_id
        return data

    @staticmethod
    def _parse_message(data: dict[str, Any]) -> Message:
        tool_calls = tuple(
            ToolCall(
                id=call["id"],
                name=call["function"]["name"],
                arguments=call["function"].get("arguments") or "{}",
            )
            for call in data.get("tool_calls") or []
        )
        return Message(
            role="assistant", content=data.get("content"), tool_calls=tool_calls
        )
