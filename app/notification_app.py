from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from core.database import supabase
from app.security_app import get_current_user

app = APIRouter()


class UpdateNotificationRequest(BaseModel):
    is_notify: bool
    remind_time: str  # "07:30" 형식


# 복습 알림 설정 수정
@app.post("/notification-push/update")
async def update_notification(
    payload: UpdateNotificationRequest,
    email: str = Depends(get_current_user),
):
    try:
        supabase.table("users") \
            .update({
                "is_notify": payload.is_notify,
                "remind_time": payload.remind_time,
            }) \
            .eq("email", email) \
            .execute()

        print(f"✅ 알림 설정 완료: {email} -> {payload.remind_time}")
        return {"status": "success", "message": "알림 설정이 저장되었습니다."}

    except Exception as e:
        print(f"❌ 알림 업데이트 에러: {e}")
        return {"status": "error", "message": str(e)}
