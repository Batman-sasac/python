from fastapi import APIRouter, Depends, Form
from core.database import supabase
from app.security_app import get_current_user

app = APIRouter()


# 복습 알림 설정 수정 (프론트 FormData: is_notify, remind_time)
@app.post("/notification-push/update")
async def update_notification(
    email: str = Depends(get_current_user),
    is_notify: str = Form(...),   # "true" / "false"
    remind_time: str = Form(...),  # "07:30" 형식
):
    try:
        is_on = is_notify.lower() in ("true", "1", "yes")
        supabase.table("users") \
            .update({
                "is_notify": is_on,
                "remind_time": remind_time,
            }) \
            .eq("email", email) \
            .execute()

        print(f"✅ 알림 설정 완료: {email} -> {remind_time}")
        return {"status": "success", "message": "알림 설정이 저장되었습니다."}

    except Exception as e:
        print(f"❌ 알림 업데이트 에러: {e}")
        return {"status": "error", "message": str(e)}
