import logging
import os
from typing import Any

import psycopg2
from supabase import Client, create_client

from core.env_loader import load_project_dotenv

load_project_dotenv()

logger = logging.getLogger(__name__)


def _supabase_credentials() -> tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
    ).strip()
    return url, key


class _LazySupabase:
    """첫 사용 시에만 Supabase 클라이언트를 만든다 (import 시점 env 미로드 방지)."""

    def __init__(self) -> None:
        self._client: Client | None = None

    def _ensure_client(self) -> Client:
        if self._client is not None:
            return self._client

        url, key = _supabase_credentials()
        if not url:
            raise RuntimeError(
                "SUPABASE_URL이 비어 있습니다. .env 또는 서버 환경변수에 "
                "SUPABASE_URL을 설정하세요."
            )
        if not key:
            raise RuntimeError(
                "Supabase API 키가 비어 있습니다. SUPABASE_SERVICE_ROLE_KEY 또는 "
                "SUPABASE_ANON_KEY를 설정하세요."
            )

        self._client = create_client(url, key)
        try:
            response = self._client.table("users").select("*").limit(1).execute()
            if response.data:
                logger.info("Supabase 연결 OK (users 샘플 %d건)", len(response.data))
            else:
                logger.warning(
                    "Supabase 연결은 됐으나 users 샘플이 비어 있음 (RLS/테이블명 확인)"
                )
        except Exception as e:
            logger.error(
                "Supabase 연결 실패: %s (SUPABASE_URL·키 설정 여부 확인)", e
            )
        return self._client

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ensure_client(), name)


supabase = _LazySupabase()
