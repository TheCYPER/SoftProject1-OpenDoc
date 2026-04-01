from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    title: str = "Untitled"
    workspace_id: str
    initial_content: dict[str, Any] | None = None


class DocumentUpdate(BaseModel):
    title: str | None = None
    content: dict[str, Any] | None = None
    status: str | None = None


class DocumentResponse(BaseModel):
    document_id: str
    workspace_id: str
    created_by: str
    title: str
    content: dict[str, Any] | None
    content_format: str
    current_revision_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    document_id: str
    title: str
    status: str
    updated_at: datetime
    created_by: str

    model_config = {"from_attributes": True}


class VersionResponse(BaseModel):
    version_id: str
    document_id: str
    base_revision_id: str | None
    reason: str | None
    created_by: str
    restored_from_version_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ShareCreate(BaseModel):
    grantee_type: str
    grantee_ref: str | None = None
    role: str
    allow_ai: bool = True
    expires_at: datetime | None = None


class ShareUpdate(BaseModel):
    role: str | None = None
    allow_ai: bool | None = None
    expires_at: datetime | None = None


class ShareResponse(BaseModel):
    share_id: str
    document_id: str
    grantee_type: str
    grantee_ref: str | None
    role: str
    allow_ai: bool
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditEventResponse(BaseModel):
    audit_event_id: str
    workspace_id: str
    document_id: str | None
    actor_user_id: str
    event_type: str
    target_ref: str | None
    metadata_json: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}
