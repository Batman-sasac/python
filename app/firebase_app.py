from fastapi import APIRouter, Depends
from core.database import supabase
from pydantic import BaseModel
from app.security_app import get_current_user
from service.notification_service import _is_expo_push_token, _token_log_snippet

app = APIRouter(prefix="/firebase", tags=["Firebase"])

class UpdateFcmTokenRequest(BaseModel):
    fcm_token: str

# FCM 토큰 저장 — 프론트: POST /firebase/user/update-fcm-token, JSON { "fcm_token": string }
@app.post("/user/update-fcm-token")
async def update_fcm_token(
    payload: UpdateFcmTokenRequest,
    email: str = Depends(get_current_user),
):
    fcm_token = (payload.fcm_token or "").strip()

    if not fcm_token:
        return {"status": "error", "message": "토큰이 없습니다."}

    try:
        is_expo = _is_expo_push_token(fcm_token)
        snippet = _token_log_snippet(fcm_token)
        print(f"📲 [토큰 저장] email={email} | 형식=ExponentPushToken(Expo)={is_expo} | {snippet}")
        if not is_expo:
            print(f"   → Android FCM 토큰으로 저장됨. iOS인데 이 로그가 보이면 프론트에서 getExpoPushTokenAsync 사용 필요.")

        supabase.table("users") \
            .update({"fcm_token": fcm_token}) \
            .eq("email", email) \
            .execute()

        print(f"📲 FCM 토큰 갱신 완료: {email}")
        return {"status": "success", "message": "FCM 토큰이 업데이트되었습니다."}

    except Exception as e:
        print(f"❌ FCM 토큰 업데이트 중 에러: {e}")
        return {"status": "error", "message": str(e)}