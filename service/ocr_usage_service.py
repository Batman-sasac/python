"""회원별 Clova OCR 페이지 사용량 관리"""

import io
from typing import Tuple
from core.database import supabase
from pypdf import PdfReader
from app.security_app import get_current_user


# 회원당 Clova OCR 페이지 사용 한도
OCR_PAGE_LIMIT = 50


def estimate_page_count(file_bytes: bytes, filename: str) -> int:
    """OCR 호출 전 페이지 수 추정 (PDF: pypdf, 이미지: 1)"""
    ext = (filename or "").split(".")[-1].lower() if "." in (filename or "") else ""
    if ext == "pdf":
        try:
            reader = PdfReader(io.BytesIO(file_bytes), strict=False)
            return len(reader.pages)
        except Exception:
            return 1
    return 1


def get_user_ocr_usage(email: str) -> int:
    """회원의 현재 OCR 페이지 사용량 반환"""
    try:
        res = (
            supabase.table("users")
            .select("ocrpages_used")
            .eq("email", email)
            .single()
            .execute()
        )

        print(f"✅ocrpages_used: {res.data}")
        return int(res.data["ocrpages_used"]) if res.data else 0
    except Exception:
        return 0


def add_ocr_usage(email: str, page_count: int) -> None:
    """회원의 OCR 사용량에 페이지 수 추가 (기존 유저 UPDATE만, social_id NOT NULL 제약 회피)"""
    current = get_user_ocr_usage(email)
    new_total = current + page_count
    supabase.table("users").update({"ocrpages_used": new_total}).eq("email", email).execute()


def check_can_use(email: str, estimated_pages: int = 1) -> Tuple[bool, int]:
    """
    OCR 사용 가능 여부 확인
    Returns: (사용가능 여부, 현재 사용량)
    """
    used = get_user_ocr_usage(email)
    return (used + estimated_pages <= OCR_PAGE_LIMIT, used)
