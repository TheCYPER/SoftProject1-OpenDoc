from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SelectionRange(BaseModel):
    from_: int = Field(alias="from", ge=0)
    to: int = Field(gt=0)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_order(self) -> "SelectionRange":
        if self.to <= self.from_:
            raise ValueError("selection_range.to must be greater than selection_range.from")
        return self


class AIJobCreate(BaseModel):
    action: str  # rewrite, summarize, translate, restructure
    scope: str = "selection"
    selection_range: SelectionRange | None = None  # ProseMirror positions from the editor selection
    selected_text: str | None = None  # text sent directly from the editor (preferred)
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
