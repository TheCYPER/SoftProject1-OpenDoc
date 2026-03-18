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

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["response"]
