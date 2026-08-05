"""회원별 Clova OCR 페이지 사용량 관리 (플랜별 월간 지급)."""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo

from core.database import supabase
from pypdf import PdfReader
from service.plan_service import PlanTier, get_plan_ocr_limit, get_user_plan
from service.subscription_service import get_subscription_for_user, is_subscription_active

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


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


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _compute_period_end(email: str) -> datetime:
    """
    OCR 사용 주기 종료 시각 (UTC).
    - 구독 active: Apple 구독 expires_at (갱신 주기)
    - free: KST 기준 달말 23:59:59.999 → 다음달 1일 00:00 KST
    """
    if is_subscription_active(email):
        sub = get_subscription_for_user(email) or {}
        exp = _parse_dt(sub.get("expires_at"))
        if exp:
            return exp

    now_kst = datetime.now(KST)
    if now_kst.month == 12:
        next_month = now_kst.replace(year=now_kst.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        next_month = now_kst.replace(month=now_kst.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return next_month.astimezone(timezone.utc)


def _fetch_user_ocr_row(email: str) -> dict:
    try:
        res = (
            supabase.table("users")
            .select(
                "ocrpages_used, ocr_page_limit, ocr_page_bonus, "
                "ocr_usage_period_end, ocr_usage_plan"
            )
            .eq("email", email)
            .single()
            .execute()
        )
        return res.data or {}
    except Exception:
        return {}


def _get_page_bonus(row: dict, plan_limit: int) -> int:
    """현재 주기 플랜 한도 위 추가 페이지 (쿠폰, 주기 리셋 시 0)."""
    if row.get("ocr_page_bonus") is not None:
        return max(0, int(row["ocr_page_bonus"]))
    legacy = row.get("ocr_page_limit")
    if legacy is not None:
        return max(0, int(legacy) - plan_limit)
    return 0


def ensure_fresh_usage_period(email: str) -> dict:
    """
    주기가 지났거나 플랜이 바뀌면 ocrpages_used 를 0으로 리셋.
    Returns: 최신 users OCR 행 일부
    """
    row = _fetch_user_ocr_row(email)
    plan_info = get_user_plan(email)
    current_plan: PlanTier = plan_info["plan"]
    period_end = _compute_period_end(email)
    stored_end = _parse_dt(row.get("ocr_usage_period_end"))
    stored_plan = row.get("ocr_usage_plan")
    now = datetime.now(timezone.utc)

    need_reset = False
    if stored_end is None:
        need_reset = True
    elif now >= stored_end:
        need_reset = True
    elif stored_plan and stored_plan != current_plan:
        need_reset = True

    if need_reset:
        payload = {
            "ocrpages_used": 0,
            "ocr_page_bonus": 0,  # 쿠폰 보너스는 당월(현재 주기)만 유효
            "ocr_usage_period_end": period_end.isoformat(),
            "ocr_usage_plan": current_plan,
        }
        try:
            supabase.table("users").update(payload).eq("email", email).execute()
            logger.info(
                "[ocr_usage] period_reset email=%s plan=%s until=%s",
                email,
                current_plan,
                period_end.isoformat(),
            )
        except Exception:
            logger.exception("[ocr_usage] period_reset_failed email=%s", email)
        row = {**row, **payload}

    return row


def get_effective_ocr_page_limit(email: str) -> int:
    """현재 주기 기준 OCR 페이지 상한 = 플랜 월간 한도 + 쿠폰 보너스."""
    row = ensure_fresh_usage_period(email)
    plan_limit = get_plan_ocr_limit(email)
    return plan_limit + _get_page_bonus(row, plan_limit)


def get_user_ocr_usage(email: str) -> int:
    """현재 주기 OCR 사용량."""
    row = ensure_fresh_usage_period(email)
    return int(row.get("ocrpages_used") or 0)


def get_ocr_page_bonus(email: str) -> int:
    row = ensure_fresh_usage_period(email)
    return _get_page_bonus(row, get_plan_ocr_limit(email))


def add_ocr_page_bonus(email: str, pages: int) -> int:
    """쿠폰: 현재 주기 한도 위 보너스 페이지 추가 (다음 주기 리셋 시 소멸)."""
    ensure_fresh_usage_period(email)
    current = get_ocr_page_bonus(email)
    new_bonus = current + pages
    try:
        supabase.table("users").update({"ocr_page_bonus": new_bonus}).eq("email", email).execute()
    except Exception as e:
        err = str(e)
        if "ocr_page_bonus" in err and ("PGRST204" in err or "schema cache" in err):
            raise RuntimeError(
                "users.ocr_page_bonus 컬럼이 없습니다. "
                "Supabase SQL Editor에서 sql/users_ocr_usage_period.sql 을 실행하세요."
            ) from e
        raise
    return get_effective_ocr_page_limit(email)


def add_ocr_usage(email: str, page_count: int) -> None:
    """OCR 사용량 추가."""
    ensure_fresh_usage_period(email)
    current = get_user_ocr_usage(email)
    supabase.table("users").update({"ocrpages_used": current + page_count}).eq("email", email).execute()


def get_ocr_usage_summary(email: str) -> dict:
    """OCR 사용량 API용 요약."""
    row = ensure_fresh_usage_period(email)
    used = int(row.get("ocrpages_used") or 0)
    plan_info = get_user_plan(email)
    plan_limit = int(plan_info["ocr_limit"])
    bonus = _get_page_bonus(row, plan_limit)
    limit = plan_limit + bonus
    period_end = _parse_dt(row.get("ocr_usage_period_end")) or _compute_period_end(email)

    return {
        "pages_used": used,
        "pages_limit": limit,
        "plan_limit": plan_limit,
        "page_bonus": bonus,
        "remaining": max(0, limit - used),
        "plan": plan_info["plan"],
        "product_id": plan_info.get("product_id"),
        "is_subscribed": plan_info["is_subscribed"],
        "period_ends_at": period_end.isoformat().replace("+00:00", "Z"),
    }


def check_can_use(email: str, estimated_pages: int = 1) -> Tuple[bool, int]:
    """OCR 사용 가능 여부. Returns: (사용가능 여부, 현재 사용량)"""
    used = get_user_ocr_usage(email)
    limit = get_effective_ocr_page_limit(email)
    return (used + estimated_pages <= limit, used)
