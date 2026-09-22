from celery import Celery

from app.config import settings

celery_app = Celery(
    "devflow", broker=settings.redis_url, backend=settings.redis_url,
    include=["app.workers.review_tasks"],
)
celery_app.conf.update(
    task_track_started=True,  # Celery result state; PostgreSQL remains job truth.
    task_acks_late=True,  # Acknowledge after execution; redelivery is possible.
    worker_prefetch_multiplier=1,  # Reserve one task per worker process.
    task_serializer="json", result_serializer="json", accept_content=["json"],
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
    task_publish_retry=False,  # Fail promptly; the persisted delivery stays pending.
)
