"""
Celery 앱 설정 - Redis를 broker로 사용
EC2 + FastAPI + Celery + Redis 구조
"""
from celery import Celery
from celery.schedules import crontab
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "notification",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["service.notification_service"],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    beat_schedule={
        "check-and-send-reminders": {
            "task": "service.notification_service.check_and_send_reminders",
            "schedule": crontab(minute="*"),  # 매 분 실행
        },
    },
)
