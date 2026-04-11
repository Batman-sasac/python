import logging
import os

import psycopg2
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

logger = logging.getLogger(__name__)

url: str = os.getenv("SUPABASE_URL")
# 백엔드 전용: service_role 사용 시 insert 후 id가 항상 반환됨 → study_logs·reward_history 저장 가능
# (ANON_KEY + RLS면 insert 반환/select가 비어서 new_id를 못 받아 리워드·로그가 안 찍힘)
key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(url, key)

try:
    response = supabase.table("users").select("*").limit(1).execute()
    if response.data:
        logger.info("Supabase 연결 OK (users 샘플 %d건)", len(response.data))
    else:
        logger.warning(
            "Supabase 연결은 됐으나 users 샘플이 비어 있음 (RLS/테이블명 확인)"
        )
except Exception as e:
    logger.error("Supabase 연결 실패: %s (SUPABASE_URL 설정 여부 확인)", e)
