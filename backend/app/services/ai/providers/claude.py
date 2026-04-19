from collections.abc import AsyncIterator
import json

import httpx

from app.services.ai.providers.base import AIProvider


class ClaudeProvider(AIProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        default_model: str = "claude-sonnet-4-20250514",
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    async def stream(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> AsyncIterator[str]:
        resolved_model = model or self._default_model
        body: dict[str, object] = {
            "model": resolved_model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if system_prompt:
            body["system"] = system_prompt

        current_event = ""
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    payload = json.loads(line[5:].strip())
                    if current_event == "content_block_delta":
                        delta = payload.get("delta") or {}
                        text = delta.get("text")
                        if isinstance(text, str) and text:
                            yield text
                    elif current_event == "error":
                        error = payload.get("error") or {}
                        message = error.get("message") or "Anthropic streaming error"
                        raise RuntimeError(str(message))
