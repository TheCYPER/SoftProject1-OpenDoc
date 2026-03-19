import httpx

from app.services.ai.providers.base import AIProvider


class OllamaProvider(AIProvider):
    def __init__(self, base_url: str = "http://ollama:11434", model: str = "qwen2.5:8b"):
        self._base_url = base_url.rstrip("/")
        self._default_model = model

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> str:
        model = model or self._default_model
        body: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["response"]
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. "
                f"Make sure Ollama is running and the model '{model}' is pulled. "
                f"In Docker: check OLLAMA_BASE_URL uses service name (http://ollama:11434), not localhost."
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(
                    f"Model '{model}' not found in Ollama. Run: docker exec -it <ollama-container> ollama pull {model}"
                )
            raise
