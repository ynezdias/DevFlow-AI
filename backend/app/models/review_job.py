import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReviewJob(Base):
    __tablename__ = "review_jobs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed', 'superseded')",
            name="ck_review_jobs_status",
        ),
        UniqueConstraint(
            "repository_name",
            "pull_request_number",
            "head_sha",
            name="uq_review_commit",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    repository_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    pull_request_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    head_sha: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="queued",
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    installation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    changed_files: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    github_repository_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    base_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scope_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    github_check_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    publication_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
