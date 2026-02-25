from fastapi import APIRouter, Depends, Form, HTTPException
from core.database import supabase
from app.security_app import get_current_user
from service.notification_service import send_push_notification, _is_expo_push_token, _token_log_snippet

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
            payload["remind_time"] = remind_time.strip()
        else:
            payload["remind_time"] = current.get("remind_time") or "07:00"

        supabase.table("users") \
            .update(payload) \
            .eq("email", email) \
            .execute()

        print(f"✅ 알림 설정 완료: {email} -> is_notify={payload['is_notify']}, remind_time={payload['remind_time']}")
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
            "message": "푸시 토큰이 등록되어 있으면 테스트 푸시를 받을 수 있습니다." if has_token else "푸시 토큰이 없습니다. iOS 앱에서 알림 권한 후 다시 시도하세요.",
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
                detail="푸시 토큰이 없습니다. iOS 앱에서 로그인한 뒤 알림 권한을 허용해주세요.",
            )
        token = (res.data["fcm_token"] or "").strip()
        is_expo = _is_expo_push_token(token)
        print(f"[테스트 푸시] email={email} | 토큰형식=Expo(iOS)={is_expo} | {_token_log_snippet(token)}")
        ok = send_push_notification(
            token=token,
            title="테스트 알림",
            body="메시지 전달 확인용 — 이 알림이 보이면 푸시가 정상 동작합니다.",
        )
        if ok:
            print(f"🔔 테스트 푸시 발송 완료: {email}")
            return {"status": "success", "message": "테스트 알림을 발송했습니다. 기기에서 수신 여부를 확인하세요."}
        # 실패 시 상세 로그는 notification_service에서 이미 출력됨
        print(f"❌ [테스트 푸시] 발송 실패: send_push_notification 반환 False | email={email} | 위 [Expo] 로그 참고")
        raise HTTPException(
            status_code=500,
            detail="푸시 발송 실패. 서버 콘솔 로그에서 [Expo] 블록으로 원인 확인.",
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ [테스트 푸시] 예외: {type(e).__name__}: {e}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


