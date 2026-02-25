from fastapi import APIRouter, Depends, Form, HTTPException
from core.database import supabase
from app.security_app import get_current_user

app = APIRouter()


# 복습 알림 설정 — 프론트: POST /notification-push/update, FormData is_notify("true"|"false"), remind_time("HH:MM")
# 보내지 않은 필드는 기존 DB 값 유지 (선택적 필드만 반영)
@app.post("/notification-push/update")
async def update_notification(
    email: str = Depends(get_current_user),
    is_notify: str | None = Form(None),   # "true" / "false" — 없으면 기존 값 유지
    remind_time: str | None = Form(None),  # "07:30" 형식 — 없거나 빈 문자열이면 기존 값 유지
):
    try:
        # 기존 값 조회 (보내지 않은 필드는 유지하기 위함)
        res = supabase.table("users") \
            .select("is_notify, remind_time") \
            .eq("email", email) \
            .single() \
            .execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
        current = res.data

        # 보낸 필드만 반영, 없으면 기존 값 유지
        payload = {}
        if is_notify is not None:
            payload["is_notify"] = is_notify.strip().lower() in ("true", "1", "yes")
        else:
            payload["is_notify"] = current.get("is_notify", False)
        if remind_time is not None and remind_time.strip():
            new_time = remind_time.strip()
            payload["remind_time"] = new_time
            # 시간을 변경하면 오늘 알림 보냄 기록 리셋 → 새 시간에 오늘도 발송 가능
            current_raw = str(current.get("remind_time") or "").strip()
            current_hm = (current_raw + ":00")[:5] if current_raw else ""
            new_hm = (new_time + ":00")[:5]
            if current_hm != new_hm:
                payload["remind_sent_at"] = None
        else:
            payload["remind_time"] = current.get("remind_time") or "07:00"

        supabase.table("users") \
            .update(payload) \
            .eq("email", email) \
            .execute()

        print(f"✅ 알림 설정 완료: {email} -> is_notify={payload['is_notify']}, remind_time={payload['remind_time']}" + (" (발송 기록 리셋)" if payload.get("remind_sent_at") is None else ""))
        return {"status": "success", "message": "알림 설정이 저장되었습니다."}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 알림 업데이트 에러: {e}")
        return {"status": "error", "message": str(e)}


# 유저 알림 설정·푸시 토큰 등록 여부 확인 (유저 확인용)
@app.get("/notification-push/me")
async def get_my_notification_status(email: str = Depends(get_current_user)):
    """로그인한 유저의 알림 설정과 푸시 토큰(Expo) 등록 여부를 반환."""
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
            "message": "푸시 토큰이 등록되어 있으면 설정한 시간에 복습 알림을 받을 수 있습니다." if has_token else "푸시 토큰이 없습니다. iOS 앱에서 알림 권한 후 다시 시도하세요.",
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"status": "error", "message": str(e)}



