"""쿠폰 검증·혜택 지급 (현재: OCR 페이지 한도 증가)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.entities.coupon import OCR_COUPON_PAGE_BONUS
from core.database import supabase
from service.ocr_usage_service import (
    add_ocr_page_bonus,
    get_effective_ocr_page_limit,
    get_user_ocr_usage,
)
from service.plan_service import get_plan_ocr_limit

logger = logging.getLogger(__name__)

BENEFIT_OCR_PAGES = "ocr_pages"


class CouponRedeemError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def _get_coupon_by_code(code: str) -> Optional[dict]:
    res = (
        supabase.table("coupons")
        .select("*")
        .eq("code", code)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def _validate_coupon(coupon: dict, email: str) -> None:
    if not coupon.get("is_active", True):
        raise CouponRedeemError("사용할 수 없는 쿠폰입니다.")

    expires_at = coupon.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if exp <= datetime.now(timezone.utc):
                raise CouponRedeemError("만료된 쿠폰입니다.")
        except ValueError:
            pass

    max_uses = coupon.get("max_uses")
    used_count = int(coupon.get("used_count") or 0)
    if max_uses is not None and used_count >= int(max_uses):
        raise CouponRedeemError("쿠폰 사용 횟수가 모두 소진되었습니다.")

    coupon_id = coupon["id"]
    existing = (
        supabase.table("coupon_redemptions")
        .select("id")
        .eq("coupon_id", coupon_id)
        .eq("user_email", email)
        .limit(1)
        .execute()
    )
    if existing.data:
        raise CouponRedeemError("이미 사용한 쿠폰입니다.", status_code=409)


def _apply_ocr_pages(email: str, pages: int) -> int:
    """현재 주기 플랜 한도 위 보너스 추가 (주기 종료 시 리셋)."""
    return add_ocr_page_bonus(email, pages)


def redeem_coupon(email: str, code: str) -> dict:
    """
    쿠폰 코드 등록. 현재 benefit_type=ocr_pages 만 지원.

    Returns:
        {
            benefit_type, pages_added, ocr_page_limit, pages_used, pages_remaining
        }
    """
    normalized = _normalize_code(code)
    if not normalized:
        raise CouponRedeemError("쿠폰 코드를 입력해주세요.")

    coupon = _get_coupon_by_code(normalized)
    if not coupon:
        raise CouponRedeemError("존재하지 않는 쿠폰 코드입니다.", status_code=404)

    _validate_coupon(coupon, email)

    benefit_type = str(coupon.get("benefit_type") or BENEFIT_OCR_PAGES)
    if benefit_type != BENEFIT_OCR_PAGES:
        raise CouponRedeemError("아직 지원하지 않는 쿠폰 유형입니다.")

    db_value = int(coupon.get("benefit_value") or 0)
    if db_value != OCR_COUPON_PAGE_BONUS:
        raise CouponRedeemError("유효하지 않은 쿠폰입니다.")

    coupon_id = coupon["id"]
    try:
        new_limit = _apply_ocr_pages(email, OCR_COUPON_PAGE_BONUS)
    except RuntimeError as e:
        raise CouponRedeemError(str(e), status_code=503) from e

    supabase.table("coupon_redemptions").insert(
        {
            "coupon_id": coupon_id,
            "user_email": email,
            "benefit_type": benefit_type,
            "benefit_value": OCR_COUPON_PAGE_BONUS,
            "redeemed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()

    supabase.table("coupons").update({"used_count": int(coupon.get("used_count") or 0) + 1}).eq(
        "id", coupon_id
    ).execute()

    used = get_user_ocr_usage(email)
    logger.info(
        "[coupon] redeemed email=%s code=%s +%s pages limit=%s",
        email,
        normalized,
        OCR_COUPON_PAGE_BONUS,
        new_limit,
    )

    return {
        "benefit_type": benefit_type,
        "pages_added": OCR_COUPON_PAGE_BONUS,
        "ocr_page_limit": new_limit,
        "pages_used": used,
        "pages_remaining": max(0, new_limit - used),
        "base_limit": get_plan_ocr_limit(email),
    }
