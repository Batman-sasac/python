"""
FastAPI routers package.

`main.py` imports routers via `from app import ...`, so this file must exist
to make `app/` a proper Python package in all environments (local, Docker, prod).
"""

from . import notification_app, ocr_app, reports_app, reward_app, study_app, user_app, weekly_app

__all__ = [
    "notification_app",
    "ocr_app",
    "reports_app",
    "reward_app",
    "study_app",
    "user_app",
    "weekly_app",
]

