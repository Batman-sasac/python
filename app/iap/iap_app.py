"""
iOS 자동 갱신 구독 IAP 라우터.

흐름:
1. 앱(StoreKit2)에서 구독 구매/복원 → transactionId를 POST /iap/verify-subscription 으로 전달
2. 서버가 App Store Server API로 상태를 직접 조회해 subscriptions 테이블에 반영
3. 갱신·해지·환불은 Apple → POST /iap/notifications (App Store Server Notifications V2)
4. 구독 활성 사용자는 product_id에 따라 OCR 페이지 한도 적용 (basic=100, pro=250)
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.security_app import get_current_user
from service.plan_service import get_user_plan
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
    """StoreKit2 구매/복원 완료 후 서버 검증 요청."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "transaction_id": "2000000123456789",
                "product_id": "com.batman.bat.basic.monthly",
            }
        }
    )

    transaction_id: str = Field(
        ...,
        min_length=5,
        description="StoreKit2 `Transaction.id` (구매/복원 직후 iOS 앱에서 전달)",
        examples=["2000000123456789"],
    )
    product_id: Optional[str] = Field(
        None,
        description="선택. App Store Connect 구독 Product ID. Apple 응답과 교차 검증.",
        examples=["com.batman.bat.basic.monthly"],
    )


PlanTier = Literal["free", "basic", "pro"]
SubStatus = Literal[
    "none", "active", "grace_period", "billing_retry", "expired", "revoked"
]


class SubscriptionStatusResponse(BaseModel):
    """구독 상태 + OCR 플랜."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "active",
                "is_active": True,
                "product_id": "com.batman.bat.basic.monthly",
                "expires_at": "2026-09-01T12:00:00+00:00",
                "auto_renew": True,
                "plan": "basic",
                "ocr_page_limit": 100,
            }
        }
    )

    status: SubStatus = Field(
        description="구독 상태. none=구독 없음, active=활성, grace_period=유예, billing_retry=결제 재시도, expired=만료, revoked=환불/취소"
    )
    is_active: bool = Field(description="OCR 플랜 혜택 적용 가능 여부 (active 또는 grace_period + 만료 전)")
    product_id: Optional[str] = Field(None, description="App Store Connect 구독 Product ID")
    expires_at: Optional[str] = Field(None, description="현재 구독 기간 종료 시각 (ISO 8601, UTC)")
    auto_renew: Optional[bool] = Field(None, description="자동 갱신 여부")
    plan: PlanTier = Field(description="OCR 플랜 tier. free=20, basic=100, pro=250 (페이지/월)")
    ocr_page_limit: int = Field(description="플랜 기준 월간 OCR 페이지 상한 (쿠폰 보너스 제외)")


def _to_status_response(sub: Optional[dict], email: Optional[str] = None) -> SubscriptionStatusResponse:
    plan_info = get_user_plan(email) if email else {"plan": "free", "ocr_limit": 20}
    if not sub:
        return SubscriptionStatusResponse(
            status="none",
            is_active=False,
            plan=plan_info["plan"],
            ocr_page_limit=plan_info["ocr_limit"],
        )
    status = str(sub.get("status") or "none")
    return SubscriptionStatusResponse(
        status=status,  # type: ignore[arg-type]
        is_active=status in ENTITLED_STATUSES,
        product_id=sub.get("product_id"),
        expires_at=sub.get("expires_at"),
        auto_renew=sub.get("auto_renew"),
        plan=plan_info["plan"],
        ocr_page_limit=plan_info["ocr_limit"],
    )


@app.post(
    "/verify-subscription",
    response_model=SubscriptionStatusResponse,
    summary="구독 구매/복원 검증",
    description=(
        "iOS 앱에서 StoreKit2 구독 **구매 또는 복원**이 완료되면 호출합니다.\n\n"
        "**프론트 연동**\n"
        "1. `Transaction.id` → `transaction_id`로 전달\n"
        "2. `Authorization: Bearer <JWT>` 필수 (로그인 사용자와 구독 연결)\n"
        "3. 성공 시 `subscriptions` 테이블 저장 + `plan`/`ocr_page_limit` 반환\n\n"
        "**멱등**: 같은 `transaction_id`로 여러 번 호출해도 Apple API 재조회 후 상태만 갱신합니다.\n\n"
        "**실패 502**: Apple API 키(`APPLE_IAP_*`) 미설정, 잘못된 transaction_id, Sandbox/Production 불일치 등."
    ),
    responses={
        400: {"description": "요청 product_id와 Apple 응답 product_id 불일치"},
        401: {"description": "JWT 없음 또는 만료"},
        502: {"description": "Apple 구독 검증 실패"},
    },
)
async def verify_subscription(
    payload: VerifySubscriptionRequest,
    email: str = Depends(get_current_user),
):
    tx = payload.transaction_id.strip()
    sub = sync_subscription_from_apple(tx, user_email=email)
    if sub is None:
        raise HTTPException(
            status_code=502,
            detail="구독 검증에 실패했습니다. 잠시 후 다시 시도해주세요.",
        )

    if payload.product_id and sub.get("product_id") and payload.product_id != sub["product_id"]:
        raise HTTPException(status_code=400, detail="product_id가 일치하지 않습니다.")

    return _to_status_response(sub, email=email)


@app.get(
    "/subscription-status",
    response_model=SubscriptionStatusResponse,
    summary="구독 상태 조회",
    description=(
        "앱 시작·설정 화면 등에서 호출. **Apple API는 호출하지 않고** DB(`subscriptions`)만 조회합니다.\n\n"
        "구매/복원 직후에는 먼저 `POST /verify-subscription`을 호출해야 최신 상태가 반영됩니다.\n\n"
        "저장된 status가 active여도 `expires_at`이 지났으면 `expired`/`is_active=false`로 응답합니다."
    ),
    responses={
        401: {"description": "JWT 없음 또는 만료"},
    },
)
async def subscription_status(email: str = Depends(get_current_user)):
    sub = get_subscription_for_user(email)
    resp = _to_status_response(sub, email=email)
    if resp.is_active and not is_subscription_active(email):
        resp.is_active = False
        resp.status = "expired"
    return resp


@app.post(
    "/notifications",
    summary="App Store Server Notifications V2 (Apple 웹훅)",
    description=(
        "App Store Connect에 등록하는 **서버-to-server 웹훅** URL입니다. "
        "iOS 앱에서 직접 호출하지 않습니다.\n\n"
        "갱신(DID_RENEW)·해지·환불(REFUND) 등 알림 수신 → `transaction_id` 추출 → "
        "Apple API 재조회 후 DB 갱신.\n\n"
        "처리 실패 시에도 **200**을 반환합니다 (Apple 재시도 방지)."
    ),
    include_in_schema=True,
)
async def app_store_notifications(request: Request):
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
