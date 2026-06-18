"""
iOS In-App Purchase (StoreKit) backend endpoints.

- 디지털 상품(소모성 토큰/구독 등)은 iOS 정책상 IAP가 일반적입니다.
- 서버는 거래(트랜잭션) 중복 처리 방지, 토큰 지급/차감의 단일 진실원천 역할을 합니다.
"""

from .iap_app import app

__all__ = ["app"]

