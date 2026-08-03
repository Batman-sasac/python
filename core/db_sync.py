"""
Supabase(PostgreSQL)에 엔티티 DDL을 적용한다.

Supabase REST(supabase-py)로는 CREATE TABLE 불가 → Postgres 직접 연결 필요.
.env 에 SUPABASE_DB_URL (또는 DATABASE_URL) 설정:

  SUPABASE_DB_URL=postgresql://postgres.[project-ref]:[password]@aws-0-....pooler.supabase.com:6543/postgres

Supabase 대시보드 → Project Settings → Database → Connection string (URI)
"""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import quote_plus

import psycopg2

from core.entities import ALL_ENTITIES
from core.entities.coupon import COUPON_DDL_STATEMENTS
from core.env_loader import load_project_dotenv

load_project_dotenv()

logger = logging.getLogger(__name__)


def _project_ref_from_supabase_url(supabase_url: str) -> str | None:
    match = re.match(r"https?://([^.]+)\.supabase\.co", supabase_url.strip())
    return match.group(1) if match else None


def get_database_url() -> str:
    """
    Postgres 연결 URI.

    우선순위:
    1) SUPABASE_DB_URL 또는 DATABASE_URL (전체 URI)
    2) SUPABASE_URL + SUPABASE_DB_PASSWORD 로 조합
    """
    url = (os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or "").strip()
    if url:
        return url

    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    password = (os.getenv("SUPABASE_DB_PASSWORD") or "").strip()
    if supabase_url and password:
        ref = _project_ref_from_supabase_url(supabase_url)
        if not ref:
            raise RuntimeError(
                "SUPABASE_URL 형식이 올바르지 않습니다 (https://xxxx.supabase.co)."
            )

        encoded_pw = quote_plus(password)
        use_pooler = (os.getenv("SUPABASE_DB_USE_POOLER") or "").lower() in (
            "1",
            "true",
            "yes",
        )
        if use_pooler:
            region = (
                os.getenv("SUPABASE_DB_POOLER_REGION") or "aws-0-ap-northeast-2"
            ).strip()
            host = f"{region}.pooler.supabase.com"
            port = (os.getenv("SUPABASE_DB_PORT") or "6543").strip()
            user = f"postgres.{ref}"
        else:
            host = (os.getenv("SUPABASE_DB_HOST") or f"db.{ref}.supabase.co").strip()
            port = (os.getenv("SUPABASE_DB_PORT") or "5432").strip()
            user = "postgres"

        return f"postgresql://{user}:{encoded_pw}@{host}:{port}/postgres"

    raise RuntimeError(
        "DB 연결 정보가 없습니다. .env 에 아래 중 하나를 설정하세요.\n"
        "  1) SUPABASE_DB_URL=postgresql://...  (Supabase → Settings → Database → URI)\n"
        "  2) SUPABASE_DB_PASSWORD=...         (Database password — API 키/service_role 아님)\n"
        "     + SUPABASE_URL (현재: "
        + ("설정됨" if supabase_url else "없음")
        + ")\n"
        "참고: SUPABASE_SECRET_KEY / SERVICE_ROLE_KEY 는 API용이라 스키마 sync 에는 쓸 수 없습니다.\n"
        "연결 없이 테이블만 만들려면 Supabase SQL Editor 에서 sql/coupons.sql 실행."
    )


def _split_sql_statements(sql: str) -> list[str]:
    parts = [p.strip() for p in re.split(r";\s*", sql.strip()) if p.strip()]
    return parts


def _collect_ddl_statements() -> list[str]:
    statements: list[str] = []
    for entity_cls in ALL_ENTITIES:
        for attr in ("DDL", "INDEX_DDL"):
            ddl = getattr(entity_cls, attr, None)
            if ddl:
                statements.extend(_split_sql_statements(ddl))
    seen: set[str] = set()
    ordered: list[str] = []
    for s in statements:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    return ordered


def _execute_statements(statements: list[str]) -> None:
    url = get_database_url()
    conn = psycopg2.connect(url)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            for stmt in statements:
                logger.info("[db_sync] execute: %s...", stmt[:80].replace("\n", " "))
                cur.execute(stmt)
    finally:
        conn.close()


def sync_all_tables() -> list[str]:
    """등록된 엔티티 DDL을 Supabase Postgres에 실행 (IF NOT EXISTS → 멱등)."""
    statements = _collect_ddl_statements()
    if not statements:
        logger.warning("[db_sync] 적용할 DDL 없음")
        return []
    _execute_statements(statements)
    logger.info("[db_sync] 완료 — %d statements", len(statements))
    return statements


def ensure_coupon_tables() -> None:
    """쿠폰 테이블만 동기화 (startup용)."""
    _execute_statements(list(COUPON_DDL_STATEMENTS))
    logger.info("[db_sync] coupon tables ensured")
