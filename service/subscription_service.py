"""
iOS 자동 갱신 구독 (App Store Server API) 상태 관리.

핵심 설계:
- 클라이언트가 보내는 transactionId, Apple 웹훅의 알림 모두 "신호"로만 쓰고,
  실제 구독 상태는 항상 App Store Server API를 서버가 직접 조회한 결과로 저장한다.
  → 웹훅 JWS 인증서 체인 검증 없이도 위조 알림으로 DB를 오염시킬 수 없다.
- 구독 식별자는 originalTransactionId (갱신돼도 불변) → subscriptions 테이블 upsert 키.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import jwt
import requests

from core.database import supabase

logger = logging.getLogger(__name__)

_PRODUCTION_BASE = "https://api.storekit.itunes.apple.com"
_SANDBOX_BASE = "https://api.storekit-sandbox.itunes.apple.com"

# App Store Server API subscription status 코드
# https://developer.apple.com/documentation/appstoreserverapi/status
_STATUS_MAP = {
    1: "active",
    2: "expired",
    3: "billing_retry",
    4: "grace_period",
    5: "revoked",
}

# OCR 무제한 등 혜택이 유지되는 상태 (유예기간 포함)
ENTITLED_STATUSES = ("active", "grace_period")


def _get_env(name: str) -> str:
    v = (os.getenv(name) or "").strip()
    if not v:
        raise RuntimeError(f"{name}가 설정되지 않았습니다.")
    return v


def _allowed_product_ids() -> set[str]:
    """구독 상품 화이트리스트 (콤마 구분). 비어 있으면 전체 허용."""
    raw = (os.getenv("APPLE_SUB_PRODUCT_IDS") or "").strip()
    return {p.strip() for p in raw.split(",") if p.strip()}


def make_app_store_token() -> str:
    """App Store Server API 호출용 JWT (ES256). bid 클레임 필수."""
    issuer_id = _get_env("APPLE_IAP_ISSUER_ID")
    key_id = _get_env("APPLE_IAP_KEY_ID")
    bundle_id = _get_env("APPLE_IAP_BUNDLE_ID")
    private_key = _get_env("APPLE_IAP_PRIVATE_KEY").replace("\\n", "\n")

    iat = int(time.time())
    payload = {
        "iss": issuer_id,
        "iat": iat,
        "exp": iat + 60 * 10,
        "aud": "appstoreconnect-v1",
        "bid": bundle_id,
    }
    headers = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


def decode_jws_payload(jws: str) -> dict:
    """
    Apple 서명 JWS의 payload 디코드 (서명 검증 생략).
    반드시 "우리가 Apple API에서 직접 받아온" JWS에만 사용할 것.
    """
    return jwt.decode(jws, options={"verify_signature": False, "verify_aud": False})


def _request_subscription_statuses(transaction_id: str) -> Optional[dict]:
    """
    GET /inApps/v1/subscriptions/{transactionId}
    production 404(거래 없음) 시 sandbox 재시도 — 앱 심사(샌드박스 결제) 대응.
    """
    token = make_app_store_token()
    headers = {"Authorization": f"Bearer {token}"}

    env = (os.getenv("APPLE_STOREKIT_ENV") or "production").strip().lower()
    bases = [_SANDBOX_BASE] if env in ("sandbox", "test") else [_PRODUCTION_BASE, _SANDBOX_BASE]

    for base in bases:
        url = f"{base}/inApps/v1/subscriptions/{transaction_id}"
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 404:
            logger.info("[sub] not_found base=%s tx=%s — 다음 환경 재시도", base, transaction_id)
            continue
        if resp.status_code >= 400:
            logger.warning(
                "[sub] apple_api_error status=%s body=%s", resp.status_code, resp.text[:500]
            )
            return None
        return resp.json()
    return None


def _pick_latest_transaction(statuses_json: dict) -> Optional[dict]:
    """
    subscriptions 응답에서 가장 최신 거래(lastTransactions) 하나를 고른다.
    {"status": int, "transaction": dict(디코드됨), "renewal": dict|None}
    """
    best: Optional[dict] = None
    for group in statuses_json.get("data") or []:
        for last_tx in group.get("lastTransactions") or []:
            signed_tx = last_tx.get("signedTransactionInfo")
            if not signed_tx:
                continue
            try:
                tx = decode_jws_payload(signed_tx)
            except Exception:
                logger.exception("[sub] tx_decode_failed")
                continue
            renewal = None
            if last_tx.get("signedRenewalInfo"):
                try:
                    renewal = decode_jws_payload(last_tx["signedRenewalInfo"])
                except Exception:
                    renewal = None
            candidate = {
                "status": int(last_tx.get("status") or 0),
                "transaction": tx,
                "renewal": renewal,
            }
            if best is None or (tx.get("expiresDate") or 0) > (
                best["transaction"].get("expiresDate") or 0
            ):
                best = candidate
    return best


def _ms_to_iso(ms: Optional[int]) -> Optional[str]:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def sync_subscription_from_apple(
    transaction_id: str, user_email: Optional[str] = None
) -> Optional[dict]:
    """
    Apple에서 구독 상태를 조회해 subscriptions 테이블에 반영.

    user_email:
    - 클라이언트 구매/복원 검증 경로에서는 토큰의 email을 전달 (신규 행 생성 가능)
    - 웹훅 경로에서는 None → 기존 행(original_transaction_id)이 있어야 갱신됨
    Returns: 저장된 구독 정보 dict 또는 None(조회 실패·미지원 상품)
    """
    statuses = _request_subscription_statuses(transaction_id)
    if not statuses:
        return None

    latest = _pick_latest_transaction(statuses)
    if not latest:
        logger.warning("[sub] no_transaction_in_response tx=%s", transaction_id)
        return None

    tx = latest["transaction"]
    product_id = tx.get("productId") or ""
    original_tx_id = str(tx.get("originalTransactionId") or "")
    if not original_tx_id:
        logger.warning("[sub] missing_original_transaction_id tx=%s", transaction_id)
        return None

    allowed = _allowed_product_ids()
    if allowed and product_id not in allowed:
        logger.warning("[sub] product_not_allowed product=%s", product_id)
        return None

    status = _STATUS_MAP.get(latest["status"], "expired")
    expires_at = _ms_to_iso(tx.get("expiresDate"))
    renewal = latest.get("renewal") or {}
    auto_renew = bool(renewal.get("autoRenewStatus", 0) == 1)
    environment = tx.get("environment") or "Production"

    row = {
        "original_transaction_id": original_tx_id,
        "product_id": product_id,
        "status": status,
        "expires_at": expires_at,
        "auto_renew": auto_renew,
        "environment": environment,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    existing = (
        supabase.table("subscriptions")
        .select("id, user_email")
        .eq("original_transaction_id", original_tx_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        owner_email = existing.data[0].get("user_email")
        # 다른 계정이 이미 소유한 구독을 가로채지 못하게 막는다
        if user_email and owner_email and owner_email != user_email:
            logger.warning(
                "[sub] owner_mismatch original_tx=%s owner=%s requester=%s",
                original_tx_id,
                owner_email,
                user_email,
            )
            return None
        supabase.table("subscriptions").update(row).eq(
            "original_transaction_id", original_tx_id
        ).execute()
        row["user_email"] = owner_email
    else:
        if not user_email:
            # 웹훅이 먼저 도착한 신규 구독 — 소유자를 모르면 저장하지 않음
            logger.info("[sub] webhook_for_unknown_subscription original_tx=%s", original_tx_id)
            return None
        row["user_email"] = user_email
        supabase.table("subscriptions").insert(row).execute()

    logger.info(
        "[sub] synced original_tx=%s product=%s status=%s expires=%s",
        original_tx_id,
        product_id,
        status,
        expires_at,
    )
    return row


def get_subscription_for_user(email: str) -> Optional[dict]:
    """사용자의 구독 중 만료가 가장 늦은 행 반환."""
    try:
        res = (
            supabase.table("subscriptions")
            .select("*")
            .eq("user_email", email)
            .order("expires_at", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception:
        logger.exception("[sub] get_subscription_failed email=%s", email)
        return None


def is_subscription_active(email: str) -> bool:
    """구독 혜택(플랜 OCR 한도) 유효 여부. active/grace_period + 만료 전."""
    sub = get_subscription_for_user(email)
    if not sub:
        return False
    if sub.get("status") not in ENTITLED_STATUSES:
        return False
    expires_at = sub.get("expires_at")
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    return exp > datetime.now(timezone.utc)
