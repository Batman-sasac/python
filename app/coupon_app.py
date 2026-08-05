# 쿠폰 API — OCR 월간 한도 +20페이지

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.security_app import get_current_user
from service.coupon_service import CouponRedeemError, redeem_coupon

logger = logging.getLogger(__name__)

app = APIRouter(prefix="/coupons", tags=["Coupons"])


class CouponRedeemRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"code": "TEST20"}})

    code: str = Field(..., min_length=1, max_length=32, description="쿠폰 코드 (대소문자 무시)")


class CouponRedeemData(BaseModel):
    benefit_type: str = Field(description="혜택 유형. 현재 `ocr_pages`만 지원")
    pages_added: int = Field(description="이번 등록으로 추가된 페이지 수 (고정 +20)")
    ocr_page_limit: int = Field(description="등록 후 월간 총 OCR 상한 (플랜 + 쿠폰 보너스)")
    pages_used: int = Field(description="현재 주기 사용량")
    pages_remaining: int = Field(description="현재 주기 남은 페이지")
    base_limit: int = Field(description="플랜 기본 월간 한도 (free=20, basic=100, pro=250)")


class CouponRedeemResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "message": "OCR 사용량이 20페이지 추가되었습니다.",
                "data": {
                    "benefit_type": "ocr_pages",
                    "pages_added": 20,
                    "ocr_page_limit": 40,
                    "pages_used": 5,
                    "pages_remaining": 35,
                    "base_limit": 20,
                },
            }
        }
    )

    status: Literal["success"] = "success"
    message: str
    data: CouponRedeemData


@app.post(
    "/redeem",
    response_model=CouponRedeemResponse,
    summary="쿠폰 등록",
    description=(
        "쿠폰 코드를 등록해 **이번 달(현재 OCR 주기) 한도에 +20페이지**를 추가합니다.\n\n"
        "- 플랜 한도 위에만 적용, **주기 종료 시 보너스 소멸** (`period_ends_at`)\n"
        "- 같은 주기 내 여러 쿠폰 등록 시 +20씩 누적\n"
        "- **1인 1쿠폰 1회** (중복 등록 409)\n"
        "- 만료·비활성·사용 횟수 초과 시 400\n\n"
        "프리 유저(20/월) + 쿠폰 1장 → 이번 달 40까지."
    ),
    responses={
        400: {"description": "만료·비활성·잘못된 코드"},
        401: {"description": "JWT 없음"},
        404: {"description": "존재하지 않는 쿠폰"},
        409: {"description": "이미 사용한 쿠폰"},
        503: {"description": "DB 컬럼 미설정 (ocr_page_bonus 등)"},
    },
)
async def redeem_coupon_api(
    data: CouponRedeemRequest,
    email: str = Depends(get_current_user),
):
    try:
        result = redeem_coupon(email, data.code)
    except CouponRedeemError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception:
        logger.exception("[coupon] redeem_failed email=%s", email)
        raise HTTPException(status_code=500, detail="쿠폰 적용에 실패했습니다.")

    return {
        "status": "success",
        "message": f"OCR 사용량이 {result['pages_added']}페이지 추가되었습니다.",
        "data": result,
    }
