"""
앱 전역 로깅 설정. LOG_LEVEL 환경변수 (DEBUG/INFO/WARNING/ERROR, 기본 INFO).
5분 알림 스케줄 등 반복 작업에서 쌓이는 서드파티 INFO 로그는 ERROR로 고정.
"""
from __future__ import annotations

import logging
import os

# APScheduler "Running job / executed successfully", httpx 요청 로그 등
_QUIET_LOGGER_NAMES = (
    "httpx",
    "httpcore",
    "urllib3",
    "apscheduler",
    "apscheduler.scheduler",
    "apscheduler.executors.default",
    "postgrest",
    "hpack",
    "asyncio",
)


def silence_noisy_loggers(*, level: int = logging.ERROR) -> None:
    for name in _QUIET_LOGGER_NAMES:
        logging.getLogger(name).setLevel(level)


def configure_logging() -> None:
    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    if not logging.root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        logging.getLogger().setLevel(level)

    silence_noisy_loggers()
