from fastapi import APIRouter, Body, Request
from pydantic import BaseModel
from typing import Optional
from database import get_db
from core.notification_service import scheduler
from datetime import datetime

app = APIRouter()


# 매 분마다 실행될 작업
def check_and_send_reminders():
    now = datetime.now().strftime("%H:%M")
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # 알림이 켜져있고, 시간이 일치하며, 토큰이 있는 유저 조회
        cur.execute("""
            SELECT email, fcm_token FROM users 
            WHERE is_notify = True AND remind_time = %s AND fcm_token IS NOT NULL
        """, (now,))
        
        targets = cur.fetchall()
        for email, token in targets:
            send_fcm_notification(
                token=token,
                title="복습할 시간입니다! 📚",
                body="오늘 공부한 내용을 잊기 전에 확인해보세요."
            )
            print(f"🔔 알림 발송 완료: {email}")
    finally:
        cur.close()
        conn.close()

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
    request : Request,
    payload: dict = Body(...)
):

    user_email = request.state.user_email
    is_notify = payload.get("is_notify")
    remind_time = payload.get("remind_time") # "07:30" 형식

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE users 
            SET is_notify = %s, remind_time = %s 
            WHERE email = %s
        """, (is_notify, remind_time, user_email))
        conn.commit()
        print(f"알림 설정 완료:{remind_time}")
        return {"status": "success", "message": "알림 설정이 저장되었습니다."}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
        conn.close()