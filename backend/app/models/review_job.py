import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReviewJob(Base):
    __tablename__ = "review_jobs"

    __table_args__ = (
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
        default=datetime.utcnow,
        nullable=False,
    )