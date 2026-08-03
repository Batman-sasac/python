"""
쿠폰 관련 Supabase(PostgreSQL) 테이블 엔티티.

OCR 쿠폰 1회 사용 시 추가 페이지 수 (coupon_service 와 공유).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

OCR_COUPON_PAGE_BONUS = 20

COUPONS_DDL = """
create table if not exists coupons (
    id bigserial primary key,
    code text not null unique,
    benefit_type text not null default 'ocr_pages',
    benefit_value int not null check (benefit_value > 0),
    max_uses int,
    used_count int not null default 0,
    expires_at timestamptz,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);
""".strip()

COUPON_REDEMPTIONS_DDL = """
create table if not exists coupon_redemptions (
    id bigserial primary key,
    coupon_id bigint not null references coupons (id),
    user_email text not null,
    benefit_type text not null,
    benefit_value int not null,
    redeemed_at timestamptz not null default now(),
    unique (coupon_id, user_email)
);
""".strip()

COUPON_REDEMPTIONS_INDEX_DDL = """
create index if not exists idx_coupon_redemptions_user_email
    on coupon_redemptions (user_email);
""".strip()


@dataclass
class CouponEntity:
    """coupons 테이블."""

    TABLE_NAME: ClassVar[str] = "coupons"
    DDL: ClassVar[str] = COUPONS_DDL

    id: Optional[int] = None
    code: str = ""
    benefit_type: str = "ocr_pages"
    benefit_value: int = OCR_COUPON_PAGE_BONUS
    max_uses: Optional[int] = None
    used_count: int = 0
    expires_at: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None


@dataclass
class CouponRedemptionEntity:
    """coupon_redemptions 테이블."""

    TABLE_NAME: ClassVar[str] = "coupon_redemptions"
    DDL: ClassVar[str] = COUPON_REDEMPTIONS_DDL
    INDEX_DDL: ClassVar[str] = COUPON_REDEMPTIONS_INDEX_DDL

    id: Optional[int] = None
    coupon_id: int = 0
    user_email: str = ""
    benefit_type: str = "ocr_pages"
    benefit_value: int = OCR_COUPON_PAGE_BONUS
    redeemed_at: Optional[str] = None


COUPON_ENTITIES = (CouponEntity, CouponRedemptionEntity)

COUPON_DDL_STATEMENTS = (
    COUPONS_DDL,
    COUPON_REDEMPTIONS_DDL,
    COUPON_REDEMPTIONS_INDEX_DDL,
)
