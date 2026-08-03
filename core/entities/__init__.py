"""DB 엔티티(테이블) 정의 — DDL + 필드 메타."""

from core.entities.coupon import COUPON_ENTITIES

ALL_ENTITIES = [*COUPON_ENTITIES]

__all__ = ["ALL_ENTITIES", "COUPON_ENTITIES"]
