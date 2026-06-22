"""
Celery application configuration.

Broker  : Redis (same instance used for session caching)
Backend : Redis (stores task results)
Beat    : Periodic task scheduler — runs alongside the worker

To start the worker:
  celery -A scheduler.celery_app worker --loglevel=info

To start the beat scheduler (in a separate terminal):
  celery -A scheduler.celery_app beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from utils.config import settings

celery_app = Celery(
    "arthsaathi",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["scheduler.nudge_tasks"],
)

celery_app.conf.update(
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,   # fair dispatch — one task at a time per worker
)

# Periodic beat schedule 

celery_app.conf.beat_schedule = {
    # Check for users with no nudge in 7+ days — runs daily at 9 AM IST
    "check-inactive-users-daily": {
        "task": "scheduler.nudge_tasks.check_inactive_users",
        "schedule": crontab(hour=9, minute=0),
    },
    # Seasonal reminder for farmer persona — runs on 1st of every month at 9 AM IST
    "seasonal-farmer-check-monthly": {
        "task": "scheduler.nudge_tasks.seasonal_farmer_check",
        "schedule": crontab(day_of_month="1", hour=9, minute=0),
    },
}
