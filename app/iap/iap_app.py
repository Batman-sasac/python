"""
iOS 자동 갱신 구독 IAP 라우터.

흐름:
1. 앱(StoreKit2)에서 구독 구매/복원 → transactionId를 POST /iap/verify-subscription 으로 전달
2. 서버가 App Store Server API로 상태를 직접 조회해 subscriptions 테이블에 반영
3. 갱신·해지·환불은 Apple → POST /iap/notifications (App Store Server Notifications V2)
   웹훅 페이로드는 신호로만 쓰고, 상태는 다시 Apple API 조회 결과로 저장 (위조 방어)
4. 구독 활성 사용자는 OCR 페이지 한도 무제한 (service.ocr_usage_service 연동)

필요 환경변수:
- APPLE_IAP_ISSUER_ID / APPLE_IAP_KEY_ID / APPLE_IAP_PRIVATE_KEY (App Store Connect API 키)
- APPLE_IAP_BUNDLE_ID (앱 번들 ID — JWT bid 클레임 필수)
- APPLE_SUB_PRODUCT_IDS (선택: 허용 구독 상품 콤마 구분)
- APPLE_STOREKIT_ENV (선택: sandbox 강제 시 "sandbox")
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.security_app import get_current_user
from service.subscription_service import (
    ENTITLED_STATUSES,
    decode_jws_payload,
    get_subscription_for_user,
    is_subscription_active,
    sync_subscription_from_apple,
)

logger = logging.getLogger(__name__)

app = APIRouter(prefix="/iap", tags=["IAP"])


class VerifySubscriptionRequest(BaseModel):
    """앱에서 구매/복원 완료 후 전달하는 StoreKit2 transactionId."""

    transaction_id: str = Field(..., min_length=5)
    product_id: Optional[str] = None


class SubscriptionStatusResponse(BaseModel):
    status: str  # none / active / grace_period / billing_retry / expired / revoked
    is_active: bool
    product_id: Optional[str] = None
    expires_at: Optional[str] = None
    auto_renew: Optional[bool] = None


def _to_status_response(sub: Optional[dict]) -> SubscriptionStatusResponse:
    if not sub:
        return SubscriptionStatusResponse(status="none", is_active=False)
    status = str(sub.get("status") or "none")
    return SubscriptionStatusResponse(
        status=status,
        is_active=status in ENTITLED_STATUSES,
        product_id=sub.get("product_id"),
        expires_at=sub.get("expires_at"),
        auto_renew=sub.get("auto_renew"),
    )


@app.post("/verify-subscription", response_model=SubscriptionStatusResponse)
async def verify_subscription(
    payload: VerifySubscriptionRequest,
    email: str = Depends(get_current_user),
):
    """
    구독 구매/복원 검증.

    transactionId로 Apple에 구독 상태를 조회해 저장하고 현재 상태를 반환한다.
    멱등: 같은 transactionId로 여러 번 호출해도 상태만 다시 동기화된다.
    """
    tx = payload.transaction_id.strip()
    sub = sync_subscription_from_apple(tx, user_email=email)
    if sub is None:
        raise HTTPException(
            status_code=502,
            detail="구독 검증에 실패했습니다. 잠시 후 다시 시도해주세요.",
        )

    if payload.product_id and sub.get("product_id") and payload.product_id != sub["product_id"]:
        raise HTTPException(status_code=400, detail="product_id가 일치하지 않습니다.")

    return _to_status_response(sub)


@app.get("/subscription-status", response_model=SubscriptionStatusResponse)
async def subscription_status(email: str = Depends(get_current_user)):
    """앱 시작 시 호출 — 서버에 저장된 구독 상태 조회 (Apple 호출 없음)."""
    sub = get_subscription_for_user(email)
    resp = _to_status_response(sub)
    # 저장된 상태가 active여도 만료 시각이 지났으면 비활성으로 응답
    if resp.is_active and not is_subscription_active(email):
        resp.is_active = False
        resp.status = "expired"
    return resp


@app.post("/notifications")
async def app_store_notifications(request: Request):
    """
    App Store Server Notifications V2 수신.

    App Store Connect에 이 URL을 등록하면 갱신(DID_RENEW)·해지·환불(REFUND) 등이 올 때마다
    Apple이 호출한다. signedPayload에서 transactionId만 꺼내고, 실제 상태는
    sync_subscription_from_apple()이 Apple API를 다시 조회해 저장한다.
    → 서명 검증 없이도 위조 요청으로는 상태를 바꿀 수 없다 (Apple 조회 결과만 저장되므로).

    주의: 200을 반환하지 않으면 Apple이 재시도하므로, 처리 실패도 200으로 응답하고 로그만 남긴다.
    """
    try:
        body = await request.json()
    except Exception:
        return {"received": True}

    signed_payload = (body or {}).get("signedPayload")
    if not signed_payload:
        return {"received": True}

    try:
        notification = decode_jws_payload(signed_payload)
    except Exception:
        logger.exception("[iap] notification_decode_failed")
        return {"received": True}

    notification_type = notification.get("notificationType")
    subtype = notification.get("subtype")

    # App Store Connect의 "테스트 알림 보내기" 응답
    if notification_type == "TEST":
        logger.info("[iap] notification TEST 수신 — 웹훅 연결 정상")
        return {"received": True}

    data = notification.get("data") or {}
    signed_tx = data.get("signedTransactionInfo")
    if not signed_tx:
        logger.info("[iap] notification without transaction type=%s", notification_type)
        return {"received": True}

    try:
        tx_payload = decode_jws_payload(signed_tx)
    except Exception:
        logger.exception("[iap] notification_tx_decode_failed type=%s", notification_type)
        return {"received": True}

    transaction_id = str(
        tx_payload.get("transactionId") or tx_payload.get("originalTransactionId") or ""
    )
    if not transaction_id:
        return {"received": True}

    logger.info(
        "[iap] notification type=%s subtype=%s tx=%s",
        notification_type,
        subtype,
        transaction_id,
    )

    try:
        sync_subscription_from_apple(transaction_id)
    except Exception:
        logger.exception("[iap] notification_sync_failed tx=%s", transaction_id)

    return {"received": True}
