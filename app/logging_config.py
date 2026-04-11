"""
앱 전역 로깅 설정. LOG_LEVEL 환경변수 (DEBUG/INFO/WARNING/ERROR, 기본 INFO).
httpx 등 시끄러운 서드파티는 WARNING으로 고정.
"""
from __future__ import annotations

import logging
import os


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

    for name in (
        "httpx",
        "httpcore",
        "urllib3",
        "apscheduler",
        "hpack",
        "asyncio",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
