import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AIInteraction(Base):
    __tablename__ = "ai_interactions"

    interaction_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.document_id"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False, default="selection")
    selection_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selection_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_revision_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_template_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_profile: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    document = relationship("Document", back_populates="ai_interactions")
    suggestion = relationship("AISuggestion", back_populates="interaction", uselist=False)
