from collections.abc import AsyncIterator
import json

import httpx

from app.services.ai.providers.base import AIProvider


class OllamaProvider(AIProvider):
    def __init__(self, base_url: str = "http://ollama:11434", model: str = "qwen2.5:8b"):
        self._base_url = base_url.rstrip("/")
        self._default_model = model

    async def stream(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> AsyncIterator[str]:
        resolved_model = model or self._default_model
        body: dict[str, object] = {
            "model": resolved_model,
            "prompt": prompt,
            "stream": True,
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/generate",
                    json=body,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        payload = json.loads(line)
                        chunk = payload.get("response")
                        if isinstance(chunk, str) and chunk:
                            yield chunk
                        if payload.get("done"):
                            break
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. "
                f"Make sure Ollama is running and the model '{resolved_model}' is pulled. "
                f"In Docker: check OLLAMA_BASE_URL uses service name (http://ollama:11434), not localhost."
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ValueError(
                    f"Model '{resolved_model}' not found in Ollama. "
                    f"Run: docker exec -it <ollama-container> ollama pull {resolved_model}"
                ) from exc
            raise
