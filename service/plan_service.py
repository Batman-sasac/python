"""사용자 OCR 플랜(무료/베이직/프로) — IAP product_id 기준."""

from __future__ import annotations

import logging
import os
from typing import Literal, Optional

from service.subscription_service import get_subscription_for_user, is_subscription_active

logger = logging.getLogger(__name__)

PlanTier = Literal["free", "basic", "pro"]

# OCR 페이지 한도
OCR_FREE_LIMIT = 20
PLAN_BASIC_OCR_LIMIT = 100
PLAN_PRO_OCR_LIMIT = 250

# 하위 호환: ocr_usage_service 등에서 import
OCR_PAGE_LIMIT = OCR_FREE_LIMIT

_PLAN_LIMITS: dict[PlanTier, int] = {
    "free": OCR_FREE_LIMIT,
    "basic": PLAN_BASIC_OCR_LIMIT,
    "pro": PLAN_PRO_OCR_LIMIT,
}


def _parse_product_id_set(env_name: str) -> set[str]:
    raw = (os.getenv(env_name) or "").strip()
    return {p.strip() for p in raw.split(",") if p.strip()}


def _basic_product_ids() -> set[str]:
    return _parse_product_id_set("APPLE_PLAN_BASIC_PRODUCT_IDS")


def _pro_product_ids() -> set[str]:
    return _parse_product_id_set("APPLE_PLAN_PRO_PRODUCT_IDS")


def plan_tier_from_product_id(product_id: Optional[str]) -> Optional[PlanTier]:
    """App Store product_id → 플랜 tier. 매핑 없으면 None."""
    if not product_id:
        return None
    pid = product_id.strip()
    if pid in _pro_product_ids():
        return "pro"
    if pid in _basic_product_ids():
        return "basic"
    return None


def get_user_plan(email: str) -> dict:
    """
    사용자 OCR 플랜 정보.

    Returns:
        plan, ocr_limit, product_id, is_subscribed
    """
    sub = get_subscription_for_user(email)
    product_id = (sub or {}).get("product_id")
    is_subscribed = is_subscription_active(email)

    if is_subscribed and product_id:
        tier = plan_tier_from_product_id(product_id)
        if tier:
            return {
                "plan": tier,
                "ocr_limit": _PLAN_LIMITS[tier],
                "product_id": product_id,
                "is_subscribed": True,
            }
        logger.warning(
            "[plan] unknown_product_id email=%s product=%s — basic(100) 적용",
            email,
            product_id,
        )
        return {
            "plan": "basic",
            "ocr_limit": PLAN_BASIC_OCR_LIMIT,
            "product_id": product_id,
            "is_subscribed": True,
        }

    return {
        "plan": "free",
        "ocr_limit": OCR_FREE_LIMIT,
        "product_id": product_id,
        "is_subscribed": False,
    }


def get_plan_ocr_limit(email: str) -> int:
    """구독 플랜 기준 OCR 페이지 상한 (쿠폰·DB 보너스 제외)."""
    return int(get_user_plan(email)["ocr_limit"])
