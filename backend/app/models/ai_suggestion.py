import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    suggestion_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    interaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_interactions.interaction_id"), nullable=False
    )
    disposition: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    accepted_segments_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    applied_revision_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    applied_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    interaction = relationship("AIInteraction", back_populates="suggestion")
