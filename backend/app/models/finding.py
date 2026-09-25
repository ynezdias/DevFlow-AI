import uuid
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint("line_number > 0", name="ck_findings_positive_line"),
        CheckConstraint("source IN ('ruff', 'bandit', 'ai')", name="ck_findings_source"),
        CheckConstraint("severity IN ('low', 'medium', 'high')", name="ck_findings_severity"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_jobs.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(Text)
    line_number: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
