from fastapi import APIRouter, Body, Depends, Form
from typing import Optional
from database import supabase
from core.notification_service import scheduler, send_fcm_notification
from apscheduler.schedulers.base import SchedulerNotRunningError
from datetime import datetime

from app.security_app import get_current_user

app = APIRouter()


# 매 분마다 실행될 작업
def check_and_send_reminders():
    now = datetime.now().strftime("%H:%M")
    try:
        # 알림이 켜져있고, 시간이 일치하며, 토큰이 있는 유저 모두 조회
        # service_role_key를 사용 중이라면 RLS를 무시하고 전체 유저를 검색합니다.
        response = supabase.table("users") \
            .select("email, fcm_token") \
            .eq("is_notify", True) \
            .eq("remind_time", now) \
            .not_.is_("fcm_token", "null") \
            .execute()
        
        targets = response.data
        
        for user in targets:
            email = user.get("email")
            token = user.get("fcm_token")
            
            # FCM 알림 발송 함수 호출
            send_fcm_notification(
                token=token,
                title="복습할 시간입니다! 📚",
                body="오늘 공부한 내용을 잊기 전에 확인해보세요."
            )
            print(f"🔔 알림 발송 완료: {email}")
            
    except Exception as e:
        print(f"❌ 스케줄러 실행 중 오류: {e}")


@app.on_event("startup")
def start_scheduler():
    if not scheduler.running:
        # 매 분(1분)마다 체크 함수 실행 등록
        scheduler.add_job(check_and_send_reminders, 'cron', minute='*')
        scheduler.start()
        print("🚀 알림 스케줄러 가동")


@app.on_event("shutdown")
def shutdown_event():
    try:
        if scheduler.running: # 스케줄러가 실행 중인지 확인
            scheduler.shutdown()
            print("🚀 스케줄러가 안전하게 종료되었습니다.")
    except SchedulerNotRunningError:
        print("⚠️ 스케줄러가 이미 종료되었거나 실행 중이 아닙니다.")

# 복습 알림 설정 수정
@app.post("/notification-push/update")
async def update_notification(
    email: str = Depends(get_current_user),
    is_notify: Optional[bool] = Form(None),
    remind_time: Optional[str] = Form(None),
    payload: Optional[dict] = Body(None),
):
    resolved_notify = payload.get("is_notify") if payload else is_notify
    resolved_time = payload.get("remind_time") if payload else remind_time
    try:
        supabase.table("users") \
            .update({
                "is_notify": resolved_notify,
                "remind_time": resolved_time
            }) \
            .eq("email", email) \
            .execute()
            
        print(f"✅ 알림 설정 완료: {email} -> {resolved_time}")
        return {"status": "success", "message": "알림 설정이 저장되었습니다."}
        
    except Exception as e:
        print(f"❌ 알림 업데이트 에러: {e}")
        return {"status": "error", "message": str(e)}