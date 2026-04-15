from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

router = APIRouter(tags=["workspaces"])

_WORKSPACE_ADMIN_ROLES = {"owner", "admin"}


class WorkspaceAIPolicyUpdate(BaseModel):
    allowed_roles_by_feature: dict[str, list[str]] | None = None
    monthly_budget: float | None = None
    per_user_quota: int | None = None


class WorkspaceResponse(BaseModel):
    workspace_id: str
    name: str
    ai_policy_json: dict[str, Any] | None

    model_config = {"from_attributes": True}


@router.patch(
    "/api/workspaces/{workspace_id}/ai-policy",
    response_model=WorkspaceResponse,
    summary="Update workspace AI policy (owner/admin only)",
)
async def update_ai_policy(
    workspace_id: str,
    body: WorkspaceAIPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update AI policy for a workspace. Requires workspace owner/admin role."""
    result = await db.execute(
        select(Workspace).where(Workspace.workspace_id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    member_result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == current_user.user_id,
        )
    )
    member = member_result.scalar_one_or_none()
    if member is None or member.workspace_role not in _WORKSPACE_ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace owner or admin role required",
        )

    existing: dict[str, Any] = dict(workspace.ai_policy_json or {})
    if body.allowed_roles_by_feature is not None:
        existing["allowed_roles_by_feature"] = body.allowed_roles_by_feature
    if body.monthly_budget is not None:
        existing["monthly_budget"] = body.monthly_budget
    if body.per_user_quota is not None:
        existing["per_user_quota"] = body.per_user_quota

    workspace.ai_policy_json = existing
    await db.commit()
    await db.refresh(workspace)
    return workspace
