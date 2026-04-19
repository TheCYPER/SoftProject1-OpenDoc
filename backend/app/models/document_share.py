import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentShare(Base):
    __tablename__ = "document_shares"
    __table_args__ = (
        CheckConstraint(
            "grantee_type IN ('USER', 'LINK')",
            name="ck_document_shares_grantee_type",
        ),
        CheckConstraint(
            "role IN ('viewer', 'editor', 'admin')",
            name="ck_document_shares_role",
        ),
    )

    share_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.document_id"), nullable=False
    )
    grantee_type: Mapped[str] = mapped_column(String(50), nullable=False)
    grantee_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    allow_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    link_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    document = relationship("Document", back_populates="shares")
