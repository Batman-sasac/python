# 쿠폰 API — 현재 OCR 페이지 한도 증가

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.security_app import get_current_user
from service.coupon_service import CouponRedeemError, redeem_coupon

logger = logging.getLogger(__name__)

app = APIRouter(prefix="/coupons", tags=["Coupons"])


class CouponRedeemRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=32, description="쿠폰 코드")


@app.post("/redeem")
async def redeem_coupon_api(
    data: CouponRedeemRequest,
    email: str = Depends(get_current_user),
):
    """쿠폰 등록 → OCR 한도 +20페이지 (1인 1회)."""
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
