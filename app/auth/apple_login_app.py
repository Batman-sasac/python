import os
import traceback
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from jwt import PyJWKClient
import jwt
from core.database import supabase
from app.security_app import create_jwt_token

app = APIRouter(prefix="/auth", tags=["Auth"])

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


class AppleLoginRequest(BaseModel):
    identity_token: str


def _verify_apple_token(identity_token: str) -> dict | None:
    """Apple identity_token JWT 검증 후 payload 반환. 실패 시 None."""
    try:
        jwks_client = PyJWKClient("https://appleid.apple.com/auth/keys")
        signing_key = jwks_client.get_signing_key_from_jwt(identity_token)
        audience = os.getenv("APPLE_CLIENT_ID") or os.getenv("APPLE_BUNDLE_ID")
        decode_kw = {"algorithms": ["RS256"]}
        if audience:
            decode_kw["audience"] = audience
        else:
            decode_kw["options"] = {"verify_audience": False}
        payload = jwt.decode(identity_token, signing_key.key, **decode_kw)
        return payload
    except Exception as e:
        print(f"[Apple 로그인] JWT 검증 실패: {e}")
        return None


@app.post("/apple/mobile")
async def apple_login_mobile(req: AppleLoginRequest):
    try:
        return await _apple_login_impl(req.identity_token)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[Apple 로그인] 예외 발생: {e}\n{tb}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "detail": str(e)},
        )


async def _apple_login_impl(identity_token: str):
    if not identity_token:
        return JSONResponse(status_code=400, content={"error": "identity_token이 필요합니다"})

    print(f"[Apple 로그인] identity_token 수신: {identity_token[:30]}...")

    payload = _verify_apple_token(identity_token)
    if not payload:
        return JSONResponse(status_code=400, content={"error": "Apple 토큰 검증 실패"})

    sub = payload.get("sub")
    if not sub:
        return JSONResponse(status_code=400, content={"error": "토큰에 sub가 없습니다"})

    social_id = f"apple_{sub}"
    user_email = payload.get("email") or f"apple_{sub}@apple.oauth"
    token = create_jwt_token(user_email, social_id)

    try:
        user_res = supabase.table("users").select("nickname").eq("social_id", social_id).execute()
        user_data = user_res.data

        if not user_data:
            try:
                supabase.table("users").insert({
                    "social_id": social_id,
                    "email": user_email,
                    "nickname": None,
                }).execute()
                print(f"[Apple 로그인] 신규 유저: {user_email}")
                return {
                    "status": "NICKNAME_REQUIRED",
                    "social_id": social_id,
                    "token": token,
                    "email": user_email,
                }
            except Exception as insert_err:
                err_str = str(insert_err)
                if "23505" in err_str or "duplicate key" in err_str.lower() or "users_email_key" in err_str:
                    print(f"[Apple 로그인] 이메일 중복 - 기존 계정에 연동: {user_email}")
                    exist_res = supabase.table("users").select("nickname, social_id").eq("email", user_email).execute()
                    if exist_res.data:
                        row = exist_res.data[0]
                        supabase.table("users").update({"social_id": social_id}).eq("email", user_email).execute()
                        nickname = row.get("nickname")
                        if not nickname:
                            return {"status": "NICKNAME_REQUIRED", "social_id": social_id, "email": user_email, "token": token}
                        return {"status": "success", "token": token, "email": user_email, "nickname": nickname}
                raise

        nickname = user_data[0].get("nickname")
        if not nickname:
            print(f"[Apple 로그인] 닉네임 없는 유저: {user_email}")
            return {
                "status": "NICKNAME_REQUIRED",
                "social_id": social_id,
                "email": user_email,
                "token": token,
            }

        print(f"[Apple 로그인] 기존 유저 로그인 성공: {nickname}")
        return {
            "status": "success",
            "token": token,
            "email": user_email,
            "nickname": nickname,
        }

    except Exception as e:
        raise
