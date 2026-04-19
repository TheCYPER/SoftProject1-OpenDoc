import asyncio
from dataclasses import dataclass


@dataclass
class ActiveAIJob:
    task: asyncio.Task[None]
    cancel_reason: str | None = None


class AIJobRegistry:
    """In-process registry for cancellable streaming AI jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, ActiveAIJob] = {}
        self._lock = asyncio.Lock()

    async def register(self, job_id: str, task: asyncio.Task[None]) -> None:
        if task.done():
            return
        async with self._lock:
            self._jobs[job_id] = ActiveAIJob(task=task)

    async def cancel(self, job_id: str, reason: str) -> bool:
        async with self._lock:
            active_job = self._jobs.get(job_id)
            if active_job is None:
                return False
            active_job.cancel_reason = reason
            return active_job.task.cancel()

    async def get_cancel_reason(self, job_id: str) -> str | None:
        async with self._lock:
            active_job = self._jobs.get(job_id)
            return None if active_job is None else active_job.cancel_reason

    async def unregister(self, job_id: str) -> None:
        async with self._lock:
            self._jobs.pop(job_id, None)


ai_job_registry = AIJobRegistry()
