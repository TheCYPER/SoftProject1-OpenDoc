from collections.abc import AsyncIterator

from app.config import settings
from app.services.ai.providers.base import AIProvider


class MockProvider(AIProvider):
    def __init__(self, response_text: str, chunk_size: int = 12):
        self._response_text = response_text
        self._chunk_size = max(1, chunk_size)

    async def stream(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> AsyncIterator[str]:
        _ = (prompt, system_prompt, model)
        text = settings.MOCK_AI_RESPONSE or self._response_text
        chunk_size = max(1, settings.MOCK_AI_CHUNK_SIZE or self._chunk_size)
        for index in range(0, len(text), chunk_size):
            yield text[index:index + chunk_size]
