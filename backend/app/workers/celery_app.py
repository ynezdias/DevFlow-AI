from celery import Celery

from app.config import settings

celery_app = Celery(
    "devflow", broker=settings.redis_url, backend=settings.redis_url,
    include=["app.workers.review_tasks", "app.workers.recovery_tasks"],
)
celery_app.conf.update(
    task_reject_on_worker_lost=True,
    task_time_limit=settings.review_task_limit_seconds,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    beat_schedule={"recover-durable-jobs": {
        "task": "app.workers.recovery_tasks.recover_reviews", "schedule": 30.0}},
    task_track_started=True,  # Celery result state; PostgreSQL remains job truth.
    task_acks_late=True,  # Acknowledge after execution; redelivery is possible.
    worker_prefetch_multiplier=1,  # Reserve one task per worker process.
    task_serializer="json", result_serializer="json", accept_content=["json"],
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3, "visibility_timeout": 7200},
    task_publish_retry=False,  # Fail promptly; the persisted delivery stays pending.
)
