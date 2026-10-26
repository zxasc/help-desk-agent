import os
from typing import Any

import httpx2
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt

from .core import Message

DEFAULT_MODEL = os.getenv("LLM_MODEL", "gemini-3.8-flash")


class LLMException(Exception):
    pass


RETRY_STATUS = {429, 500, 502, 503, 504}


class LLMClient:
    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL,
        timeout: float = 30.0,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        max_retries: int = 3,
    ):
        self.model = model_name
        self.temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._api_key = os.getenv("LLM_API_KEY")
        self._api_url = os.getenv("LLM_API_URL")
        self._http = httpx2.AsyncClient(
            base_url=str(self._api_key).rstrip("/") + "/",
            headers={"Authorization": f"Bearer {self._api_key}"}
            if self._api_key
            else {},
            timeout=timeout,
            transport=httpx2.AsyncHTTPTransport(retries=3),
        )

    async def __call__(self, messages: list[Message]) -> str:
        payload = self._create_payload(messages)

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries),
                retry=retry_if_exception_type(httpx2.HTTPError),
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

        if response.is_error:
            raise LLMException(
                f"Provider returned HTTP {response.status_code}: {response.text[:500]}"
            )
        return response.json()

    def _create_payload(self, messages: list[Message]) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": self._max_tokens,
        }
