from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

AIProviderName = Literal["openai", "groq", "claude", "ollama"]
AIActionName = Literal["rewrite", "summarize", "translate", "restructure"]


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
    action: AIActionName
    scope: str = "selection"
    selection_range: SelectionRange | None = None  # ProseMirror positions from the editor selection
    selected_text: str | None = None  # text sent directly from the editor (preferred)
    base_revision_id: str | None = None
    options: dict[str, Any] | None = None

    provider: AIProviderName | None = None
    model: str | None = None

    # Backwards compatibility: ignore legacy client-side secret/base_url fields if sent.
    model_config = {"extra": "ignore"}


class AIJobResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    provider_name: str | None = None
    model_name: str | None = None
    prompt_template_version: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class AISuggestionResponse(BaseModel):
    suggestion_id: str
    original_text: str | None
    suggested_text: str | None
    diff_json: dict[str, Any] | None
    stale: bool
    disposition: str
    partial_output_available: bool = False

    model_config = {"from_attributes": True}


class AIJobApply(BaseModel):
    mode: str = "full"
    selected_diff_blocks: list[int] | None = None
    target_revision_id: str | None = None


class AIJobCancelResponse(BaseModel):
    job_id: str
    status: str
    completed_at: datetime | None = None


class AIHistoryItem(BaseModel):
    job_id: str
    suggestion_id: str | None = None
    action: str
    scope: str
    status: str
    disposition: str | None = None
    stale: bool
    original_text: str | None = None
    suggested_text: str | None = None
    partial_output_available: bool = False
    prompt_template_version: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    prompt_text: str | None = None
    system_prompt_text: str | None = None
    requested_by_user_id: str
    requested_by_display_name: str | None = None
    requested_by_email: str | None = None
    selection_range: SelectionRange | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AIHistoryResponse(BaseModel):
    items: list[AIHistoryItem]
