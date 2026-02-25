from fastapi import APIRouter, Depends
from core.database import supabase
from pydantic import BaseModel
from app.security_app import get_current_user
from service.notification_service import _is_expo_push_token, _token_log_snippet

app = APIRouter(prefix="/firebase", tags=["Firebase"])

class UpdateFcmTokenRequest(BaseModel):
    fcm_token: str  # DB 컬럼명 호환용. 실제로는 Expo push token (ExponentPushToken)

# Expo 푸시 토큰 저장 — 프론트(iOS): POST /firebase/user/update-fcm-token, JSON { "fcm_token": "ExponentPushToken[...]" }
@app.post("/user/update-fcm-token")
async def update_fcm_token(
    payload: UpdateFcmTokenRequest,
    email: str = Depends(get_current_user),
):
    push_token = (payload.fcm_token or "").strip()

    if not push_token:
        return {"status": "error", "message": "토큰이 없습니다."}

    try:
        if not _is_expo_push_token(push_token):
            print(f"📲 [토큰 저장] ❌ ExponentPushToken이 아님 — 거부 | email={email} | {_token_log_snippet(push_token)}")
            return {"status": "error", "message": "Expo 푸시 토큰(ExponentPushToken)만 등록 가능합니다."}

        snippet = _token_log_snippet(push_token)
        print(f"📲 [토큰 저장] email={email} | Expo 푸시 토큰 | {snippet}")

        supabase.table("users") \
            .update({"fcm_token": push_token}) \
            .eq("email", email) \
            .execute()

        print(f"📲 푸시 토큰 갱신 완료: {email}")
        return {"status": "success", "message": "푸시 토큰이 업데이트되었습니다."}

    except Exception as e:
        print(f"❌ 푸시 토큰 업데이트 중 에러: {e}")
        return {"status": "error", "message": str(e)}