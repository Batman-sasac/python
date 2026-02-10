import os
import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Header, HTTPException

def create_jwt_token(email: str, social_id: str) -> str:
    secret_key = os.getenv("JWT_SECRET_KEY", "default_secret")
    payload = {
        "email": email,
        "social_id": social_id,
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 헤더가 누락되었거나 Bearer 형식이 아닙니다.")

    token = authorization.split(" ", 1)[1].strip().replace('"', '').replace("'", '')
    secret_key = os.getenv("JWT_SECRET_KEY", "default_secret")

    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        email = payload.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
        return email
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"유효하지 않은 토큰입니다: {exc}")