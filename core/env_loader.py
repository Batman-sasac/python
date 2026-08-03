"""프로젝트 루트 .env 로드 (uvicorn/gunicorn 실행 cwd와 무관)."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


def load_project_dotenv() -> Path:
    """루트 `.env`를 로드한다.

    override=True: 셸에 SUPABASE_URL= 처럼 빈 값이 잡혀 있으면 기본 load_dotenv는
    .env를 덮어쓰지 않아 Supabase URL이 계속 비는 경우가 있다.
    """
    if _ENV_FILE.is_file():
        load_dotenv(_ENV_FILE, override=True)
    return _ENV_FILE


def supabase_api_key() -> str:
    """REST API용 Supabase 키 (service_role 우선)."""
    import os

    return (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SECRET_KEY")  # .env 별칭 (구 naming)
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    ).strip()


def supabase_env_status() -> dict[str, bool | str]:
    import os

    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = supabase_api_key()
    return {
        "env_file": str(_ENV_FILE),
        "env_file_exists": _ENV_FILE.is_file(),
        "supabase_url_set": bool(url),
        "supabase_key_set": bool(key),
        "supabase_url_host": url.split("//")[-1].split("/")[0][:80] if url else "",
    }
