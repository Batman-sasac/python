from fastapi import APIRouter, Request, Body
from database import supabase

app = APIRouter()

#users DB fcm_token 저장
@app.post("/user/update-fcm-token")
async def update_fcm_token(request: Request, payload: dict = Body(...)):
    user_email = request.state.user_email # 미들웨어에서 추출
    fcm_token = payload.get("fcm_token")
    
    if not fcm_token:
        return {"status": "error", "message": "토큰이 없습니다."}

    try:
        # 2. SDK 버전 업데이트
        # .eq("email", user_email)를 통해 정확히 해당 유저의 토큰만 갱신합니다.
        supabase.table("users") \
            .update({"fcm_token": fcm_token}) \
            .eq("email", user_email) \
            .execute()
        
        print(f"📲 FCM 토큰 갱신 완료: {user_email}")
        return {"status": "success", "message": "FCM 토큰이 업데이트되었습니다."}
        
    except Exception as e:
        print(f"❌ FCM 토큰 업데이트 중 에러: {e}")
        return {"status": "error", "message": str(e)}