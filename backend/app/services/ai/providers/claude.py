import httpx

from app.services.ai.providers.base import AIProvider


class ClaudeProvider(AIProvider):
    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com"):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> str:
        model = model or "claude-sonnet-4-20250514"
        body: dict = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            body["system"] = system_prompt

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base_url}/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]
