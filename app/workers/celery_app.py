from __future__ import annotations

from celery import Celery

from config.settings import settings

celery_app = Celery(
    "heyroya",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.analyze", "app.workers.correct"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
)
