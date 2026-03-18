from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AIJobCreate(BaseModel):
    action: str  # rewrite, summarize, translate, restructure
    scope: str = "selection"
    selection_range: dict[str, int] | None = None  # {"from": 120, "to": 480}
    base_revision_id: str | None = None
    options: dict[str, Any] | None = None

    # AI provider override (optional — user can bring their own key)
    provider: str | None = None  # openai, claude, ollama
    api_key: str | None = None
    base_url: str | None = None


class AIJobResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AISuggestionResponse(BaseModel):
    suggestion_id: str
    original_text: str | None
    suggested_text: str | None
    diff_json: dict[str, Any] | None
    stale: bool
    disposition: str

    model_config = {"from_attributes": True}


class AIJobApply(BaseModel):
    mode: str = "full"
    selected_diff_blocks: list[int] | None = None
    target_revision_id: str | None = None
