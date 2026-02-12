from fastapi import APIRouter, Depends, Form, HTTPException
from core.database import supabase
from app.security_app import get_current_user
from service.notification_service import send_fcm_notification

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


# 유저 알림 설정·FCM 토큰 확인 (유저 확인용)
@app.get("/notification-push/me")
async def get_my_notification_status(email: str = Depends(get_current_user)):
    """로그인한 유저의 알림 설정과 FCM 토큰 존재 여부를 반환."""
    try:
        res = supabase.table("users") \
            .select("email, is_notify, remind_time, fcm_token") \
            .eq("email", email) \
            .single() \
            .execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
        row = res.data
        has_token = bool(row.get("fcm_token"))
        return {
            "status": "success",
            "email": row.get("email"),
            "is_notify": row.get("is_notify", False),
            "remind_time": row.get("remind_time"),
            "fcm_token_registered": has_token,
            "message": "FCM 토큰이 등록되어 있으면 테스트 푸시를 받을 수 있습니다." if has_token else "FCM 토큰이 없습니다. 앱에서 알림 권한 후 다시 시도하세요.",
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"status": "error", "message": str(e)}


# 테스트 푸시 발송 — 메시지 전달 여부 확인용
@app.post("/notification-push/test")
async def send_test_notification(email: str = Depends(get_current_user)):
    """현재 유저의 기기로 테스트 알림을 한 번 보냅니다. 유저 확인 다음 메시지 전달 확인용."""
    try:
        res = supabase.table("users") \
            .select("fcm_token") \
            .eq("email", email) \
            .single() \
            .execute()
        if not res.data or not res.data.get("fcm_token"):
            raise HTTPException(
                status_code=400,
                detail="FCM 토큰이 없습니다. 앱에서 로그인한 뒤 알림 권한을 허용해주세요.",
            )
        token = res.data["fcm_token"]
        ok = send_fcm_notification(
            token=token,
            title="테스트 알림",
            body="메시지 전달 확인용 — 이 알림이 보이면 푸시가 정상 동작합니다.",
        )
        if ok:
            print(f"🔔 테스트 푸시 발송 완료: {email}")
            return {"status": "success", "message": "테스트 알림을 발송했습니다. 기기에서 수신 여부를 확인하세요."}
        raise HTTPException(status_code=500, detail="FCM 발송에 실패했습니다.")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 테스트 푸시 에러: {e}")
        return {"status": "error", "message": str(e)}
