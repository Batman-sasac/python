from fastapi import APIRouter, Body, Depends, Form
from typing import Optional
from database import supabase

from app.security_app import get_current_user

app = APIRouter()

#users DB fcm_token 저장
@app.post("/user/update-fcm-token")
async def update_fcm_token(
    email: str = Depends(get_current_user),
    fcm_token: Optional[str] = Form(None),
    payload: Optional[dict] = Body(None),
):
    resolved_token = payload.get("fcm_token") if payload else fcm_token
    
    if not resolved_token:
        return {"status": "error", "message": "토큰이 없습니다."}

    try:
        # 2. SDK 버전 업데이트
        # .eq("email", user_email)를 통해 정확히 해당 유저의 토큰만 갱신합니다.
        supabase.table("users") \
            .update({"fcm_token": resolved_token}) \
            .eq("email", email) \
            .execute()
        
        print(f"📲 FCM 토큰 갱신 완료: {email}")
        return {"status": "success", "message": "FCM 토큰이 업데이트되었습니다."}
        
    except Exception as e:
        print(f"❌ FCM 토큰 업데이트 중 에러: {e}")
        return {"status": "error", "message": str(e)}