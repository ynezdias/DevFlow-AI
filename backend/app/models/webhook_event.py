from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import DateTime, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    delivery_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    review_id: Mapped[UUID | None] = mapped_column(ForeignKey("review_jobs.id", name="fk_webhook_events_review_id"), nullable=True)
