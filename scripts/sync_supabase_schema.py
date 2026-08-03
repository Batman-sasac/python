#!/usr/bin/env python3
"""Supabase Postgres에 엔티티 테이블 DDL 적용.

사용법 (프로젝트 루트):
  python scripts/sync_supabase_schema.py

필수 .env:
  SUPABASE_DB_URL=postgresql://...
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db_sync import sync_all_tables  # noqa: E402


def main() -> int:
    try:
        applied = sync_all_tables()
    except Exception as e:
        print(f"❌ 스키마 동기화 실패: {e}")
        return 1
    print(f"✅ 스키마 동기화 완료 ({len(applied)} statements)")
    for s in applied:
        first_line = s.split("\n", 1)[0][:70]
        print(f"  - {first_line}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
