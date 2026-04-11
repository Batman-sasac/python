import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException

# .env는 프로젝트 루트 기준으로 로드 (app/security_app.py -> 한 단계 위가 루트)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logger = logging.getLogger(__name__)

# ✅ 1. 설정값 통일 (변수명을 JWT_SECRET_KEY로 통일)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY or not JWT_SECRET_KEY.strip():
    raise RuntimeError(
        "JWT_SECRET_KEY가 .env에 설정되지 않았습니다. "
        "bat_python/.env 파일에 JWT_SECRET_KEY=... 를 추가하세요."
    )
ALGORITHM = "HS256"


# ✅ 2. 토큰 생성 함수 (기존 코드 유지 또는 참고)
def create_jwt_token(email: str, social_id: str):
    payload = {
        "email": email,
        "social_id": social_id,
        "exp": datetime.utcnow() + timedelta(days=30)  # 1일 동안 유효
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)


# ✅ 3. 핵심: 토큰 검증 및 사용자 추출 함수
async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        logger.debug("Authorization 헤더 없음")
        raise HTTPException(status_code=401, detail="인증 헤더가 누락되었습니다.")

    if not authorization.startswith("Bearer "):
        logger.debug("Bearer 형식 아님")
        raise HTTPException(status_code=401, detail="'Bearer ' 형식이 아닙니다.")

    try:
        token = authorization.split(" ")[1].strip().replace('"', '').replace("'", "")
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])

        email = payload.get("email")
        if not email:
            logger.warning("토큰 페이로드에 email 없음")
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰 페이로드입니다.")

        return email

    except jwt.ExpiredSignatureError:
        logger.debug("JWT 만료")
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError as e:
        logger.warning("JWT 검증 실패: %s", e)
        raise HTTPException(status_code=401, detail=f"유효하지 않은 토큰입니다. 이유: {str(e)}")
    except Exception:
        logger.exception("인증 처리 오류")
        raise HTTPException(status_code=500, detail="서버 인증 처리 중 오류가 발생했습니다.")
