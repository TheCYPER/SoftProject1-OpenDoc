import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.workspace_id"), nullable=False
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="Untitled")
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_format: Mapped[str] = mapped_column(
        String(50), nullable=False, default="prosemirror-json"
    )
    current_revision_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    workspace = relationship("Workspace", back_populates="documents")
    creator = relationship("User", back_populates="documents")
    shares = relationship("DocumentShare", back_populates="document")
    versions = relationship("DocumentVersion", back_populates="document")
    ai_interactions = relationship("AIInteraction", back_populates="document")
